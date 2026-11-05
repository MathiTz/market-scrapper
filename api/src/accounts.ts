/**
 * Accounts: e-mail + password (and Google) sign-in, saved shopping lists and the preferred
 * place a person compares prices from ("Perto de você").
 *
 * The public snapshot stays read-only; only this module writes, and only to the account tables
 * (see scraping/db/schema.sql). Passwords are PBKDF2-SHA-256; the session cookie carries a random
 * token whose SHA-256 hash is what the database stores, so a leaked session table cannot be replayed.
 */
import { Hono, type Context } from "hono";
import { deleteCookie, getCookie, setCookie } from "hono/cookie";
import postgres from "postgres";

export type Account = {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
};

/** The reference the "Perto de você" filter uses: saved per account so it follows the person. */
export type PreferredLocation = {
  label: string;
  latitude: number;
  longitude: number;
  radius_km: number;
};

export type Preferences = {
  /** Covered city the person is browsing ("Fortaleza"). */
  region: string;
  location: PreferredLocation | null;
};

/** One line of a saved list, the same shape the browser keeps in localStorage (web/lib/list-storage.ts). */
export type SavedLine = {
  product_id: string;
  name: string;
  quantity: number;
  checked: boolean;
};

export type SavedList = {
  id: string;
  name: string;
  lines: SavedLine[];
  created_at: string;
  updated_at: string;
};

export type NewAccount = {
  email: string;
  password_hash: string | null;
  name: string | null;
  google_sub: string | null;
};

/** Where accounts are read and written. Implementations: Postgres (production) and memory (tests/preview). */
export interface AccountStore {
  createUser(input: NewAccount): Promise<Account>;
  /** The account and its password hash (null for a Google-only account), or null when there is none. */
  userByEmail(email: string): Promise<{ account: Account; password_hash: string | null } | null>;
  userByGoogleSub(sub: string): Promise<Account | null>;
  /** Connects a Google identity to an account that already exists with the same verified e-mail. */
  linkGoogle(userId: string, sub: string): Promise<Account>;
  createSession(tokenHash: string, userId: string, expiresAt: Date): Promise<void>;
  sessionUser(tokenHash: string): Promise<Account | null>;
  deleteSession(tokenHash: string): Promise<void>;
  preferences(userId: string): Promise<Preferences>;
  savePreferences(userId: string, preferences: Preferences): Promise<Preferences>;
  lists(userId: string): Promise<SavedList[]>;
  createList(userId: string, name: string, lines: SavedLine[]): Promise<SavedList>;
  updateList(userId: string, id: string, name: string, lines: SavedLine[]): Promise<SavedList | null>;
  deleteList(userId: string, id: string): Promise<boolean>;
}

/** A second account with the same e-mail: the caller answers 409, not 500. */
export class AccountExistsError extends Error {
  constructor() {
    super("An account with this e-mail already exists");
    this.name = "AccountExistsError";
  }
}

export const DEFAULT_PREFERENCES: Preferences = { region: "Fortaleza", location: null };

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 200;
export const MAX_EMAIL = 254;
export const MAX_NAME = 80;
export const MAX_LIST_NAME = 80;
export const MAX_LISTS = 20;
export const MAX_LINES = 200;
export const MAX_QUANTITY = 999;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const SESSION_COOKIE = "med_session";
const OAUTH_COOKIE = "med_oauth_state";
const SESSION_DAYS = 30;
const PBKDF2_ITERATIONS = 210_000;

/* -------------------------------------------------------------------------------------------- */
/* Validation                                                                                    */
/* -------------------------------------------------------------------------------------------- */

export function normalizeEmail(raw: unknown): string {
  return typeof raw === "string" ? raw.trim().toLowerCase() : "";
}

export function emailProblem(email: string): string | null {
  if (!email) return "Informe um e-mail.";
  if (email.length > MAX_EMAIL) return "O e-mail pode ter no máximo 254 caracteres.";
  if (!EMAIL.test(email)) return "Digite um e-mail válido, como nome@exemplo.com.";
  return null;
}

export function passwordProblem(password: unknown): string | null {
  if (typeof password !== "string" || password.length < MIN_PASSWORD)
    return `A senha precisa ter pelo menos ${MIN_PASSWORD} caracteres.`;
  if (password.length > MAX_PASSWORD) return `A senha pode ter no máximo ${MAX_PASSWORD} caracteres.`;
  return null;
}

/** The display name, `null` when left empty, or `undefined` when it is too long for the column. */
export function cleanName(raw: unknown): string | null | undefined {
  if (raw === undefined || raw === null) return null;
  if (typeof raw !== "string") return null;
  const name = raw.trim();
  if (!name) return null;
  return name.length <= MAX_NAME ? name : undefined;
}

export function cleanListName(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const name = raw.trim();
  return name && name.length <= MAX_LIST_NAME ? name : null;
}

/** The lines as stored, or null when the payload is not a list of valid lines. */
export function sanitizeLines(input: unknown): SavedLine[] | null {
  if (!Array.isArray(input) || input.length > MAX_LINES) return null;
  const lines: SavedLine[] = [];
  for (const item of input) {
    if (!item || typeof item !== "object") return null;
    const line = item as Record<string, unknown>;
    if (typeof line.product_id !== "string" || !line.product_id || line.product_id.length > 200) return null;
    if (!Number.isInteger(line.quantity) || (line.quantity as number) < 1 || (line.quantity as number) > MAX_QUANTITY)
      return null;
    lines.push({
      product_id: line.product_id,
      name: typeof line.name === "string" && line.name.trim() ? line.name.trim().slice(0, 200) : "Item salvo",
      quantity: line.quantity as number,
      checked: line.checked === true,
    });
  }
  return lines;
}

/** Region + preferred location, or null when the payload is malformed. */
export function sanitizePreferences(input: unknown): Preferences | null {
  if (!input || typeof input !== "object") return null;
  const body = input as Record<string, unknown>;
  const region = typeof body.region === "string" && body.region.trim() ? body.region.trim() : DEFAULT_PREFERENCES.region;
  if (region.length > MAX_NAME) return null;
  if (body.location === null || body.location === undefined) return { region, location: null };
  if (typeof body.location !== "object") return null;
  const location = body.location as Record<string, unknown>;
  const label = typeof location.label === "string" ? location.label.trim() : "";
  const { latitude, longitude, radius_km: radius } = location;
  const valid =
    label.length > 0 &&
    label.length <= 200 &&
    typeof latitude === "number" &&
    Number.isFinite(latitude) &&
    Math.abs(latitude) <= 90 &&
    typeof longitude === "number" &&
    Number.isFinite(longitude) &&
    Math.abs(longitude) <= 180 &&
    typeof radius === "number" &&
    Number.isInteger(radius) &&
    radius >= 1 &&
    radius <= 50;
  if (!valid) return null;
  return {
    region,
    location: {
      label,
      latitude: latitude as number,
      longitude: longitude as number,
      radius_km: radius as number,
    },
  };
}

/* -------------------------------------------------------------------------------------------- */
/* Crypto                                                                                        */
/* -------------------------------------------------------------------------------------------- */

const encoder = new TextEncoder();

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function toBase64Url(bytes: Uint8Array): string {
  return toBase64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomToken(bytes = 32): string {
  return toBase64Url(crypto.getRandomValues(new Uint8Array(bytes)));
}

/** `pbkdf2-sha256$<iterations>$<salt>$<hash>`, all binary parts base64. */
export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const bits = await derive(password, salt, PBKDF2_ITERATIONS);
  return `pbkdf2-sha256$${PBKDF2_ITERATIONS}$${toBase64(salt)}$${toBase64(bits)}`;
}

async function derive(password: string, salt: Uint8Array, iterations: number): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations },
    key,
    256,
  );
  return new Uint8Array(bits);
}

export async function verifyPassword(password: string, stored: string | null): Promise<boolean> {
  if (!stored) return false;
  const [scheme, iterations, salt, hash] = stored.split("$");
  if (scheme !== "pbkdf2-sha256" || !iterations || !salt || !hash) return false;
  const count = Number(iterations);
  if (!Number.isInteger(count) || count < 1 || count > 1_000_000) return false;
  const expected = fromBase64(hash);
  const actual = await derive(password, fromBase64(salt), count);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

function timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean {
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** What the sessions table stores: a token hash, never the token itself. */
export async function hashToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(token));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/* -------------------------------------------------------------------------------------------- */
/* Postgres                                                                                      */
/* -------------------------------------------------------------------------------------------- */

type UserRow = { id: string; email: string; name: string | null; created_at: Date };
type SessionUserRow = UserRow & { password_hash: string | null };
type ListRow = { id: string; name: string; lines: SavedLine[]; created_at: Date; updated_at: Date };
type PreferencesRow = {
  region: string;
  location_label: string | null;
  latitude: number | null;
  longitude: number | null;
  radius_km: number | null;
};

const account = (row: UserRow): Account => ({
  id: row.id,
  email: row.email,
  name: row.name,
  created_at: row.created_at.toISOString(),
});

const savedList = (row: ListRow): SavedList => ({
  id: row.id,
  name: row.name,
  lines: Array.isArray(row.lines) ? row.lines : [],
  created_at: row.created_at.toISOString(),
  updated_at: row.updated_at.toISOString(),
});

const isDuplicate = (error: unknown) => (error as { code?: string } | null)?.code === "23505";

/** Accounts in Postgres (through Hyperdrive on Cloudflare). One short-lived client per operation. */
export function postgresAccountStore(connectionString: string): AccountStore {
  async function query<T>(run: (sql: postgres.Sql) => Promise<T>): Promise<T> {
    // No prepared statements: they do not survive a pooler (Hyperdrive, Neon's pgbouncer) in between.
    const sql = postgres(connectionString, { max: 1, fetch_types: false, prepare: false });
    try {
      return await run(sql);
    } finally {
      await sql.end({ timeout: 1 });
    }
  }

  return {
    async createUser(input) {
      try {
        const [row] = await query((sql) =>
          sql<UserRow[]>`
            INSERT INTO users (id, email, password_hash, name, google_sub)
            VALUES (${crypto.randomUUID()}, ${input.email}, ${input.password_hash}, ${input.name}, ${input.google_sub})
            RETURNING id, email, name, created_at`,
        );
        return account(row);
      } catch (error) {
        if (isDuplicate(error)) throw new AccountExistsError();
        throw error;
      }
    },

    async userByEmail(email) {
      const [row] = await query((sql) =>
        sql<SessionUserRow[]>`
          SELECT id, email, name, created_at, password_hash FROM users WHERE email = ${email}`,
      );
      return row ? { account: account(row), password_hash: row.password_hash } : null;
    },

    async userByGoogleSub(sub) {
      const [row] = await query((sql) =>
        sql<UserRow[]>`SELECT id, email, name, created_at FROM users WHERE google_sub = ${sub}`,
      );
      return row ? account(row) : null;
    },

    async linkGoogle(userId, sub) {
      const [row] = await query((sql) =>
        sql<UserRow[]>`
          UPDATE users SET google_sub = ${sub} WHERE id = ${userId}
          RETURNING id, email, name, created_at`,
      );
      // The account was read a moment ago; a missing row means it was deleted in between.
      if (!row) throw new Error("Account not found");
      return account(row);
    },

    async createSession(tokenHash, userId, expiresAt) {
      await query((sql) =>
        sql`INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (${tokenHash}, ${userId}, ${expiresAt})`,
      );
    },

    async sessionUser(tokenHash) {
      const [row] = await query((sql) =>
        sql<UserRow[]>`
          SELECT u.id, u.email, u.name, u.created_at
          FROM sessions s JOIN users u ON u.id = s.user_id
          WHERE s.token_hash = ${tokenHash} AND s.expires_at > now()`,
      );
      return row ? account(row) : null;
    },

    async deleteSession(tokenHash) {
      await query((sql) => sql`DELETE FROM sessions WHERE token_hash = ${tokenHash}`);
    },

    async preferences(userId) {
      const [row] = await query((sql) =>
        sql<PreferencesRow[]>`
          SELECT region, location_label, latitude, longitude, radius_km
          FROM user_preferences WHERE user_id = ${userId}`,
      );
      if (!row) return { ...DEFAULT_PREFERENCES };
      return {
        region: row.region,
        location:
          row.location_label && row.latitude !== null && row.longitude !== null && row.radius_km !== null
            ? {
                label: row.location_label,
                latitude: row.latitude,
                longitude: row.longitude,
                radius_km: row.radius_km,
              }
            : null,
      };
    },

    async savePreferences(userId, preferences) {
      const place = preferences.location;
      await query((sql) =>
        sql`
          INSERT INTO user_preferences (user_id, region, location_label, latitude, longitude, radius_km, updated_at)
          VALUES (${userId}, ${preferences.region}, ${place?.label ?? null}, ${place?.latitude ?? null},
                  ${place?.longitude ?? null}, ${place?.radius_km ?? null}, now())
          ON CONFLICT (user_id) DO UPDATE SET
            region = EXCLUDED.region,
            location_label = EXCLUDED.location_label,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            radius_km = EXCLUDED.radius_km,
            updated_at = now()`,
      );
      return preferences;
    },

    async lists(userId) {
      const rows = await query((sql) =>
        sql<ListRow[]>`
          SELECT id, name, lines, created_at, updated_at FROM saved_lists
          WHERE user_id = ${userId} ORDER BY updated_at DESC`,
      );
      return rows.map(savedList);
    },

    async createList(userId, name, lines) {
      const [row] = await query((sql) =>
        sql<ListRow[]>`
          INSERT INTO saved_lists (id, user_id, name, lines)
          VALUES (${crypto.randomUUID()}, ${userId}, ${name}, ${sql.json(lines)})
          RETURNING id, name, lines, created_at, updated_at`,
      );
      return savedList(row);
    },

    async updateList(userId, id, name, lines) {
      const [row] = await query((sql) =>
        sql<ListRow[]>`
          UPDATE saved_lists SET name = ${name}, lines = ${sql.json(lines)}, updated_at = now()
          WHERE id = ${id} AND user_id = ${userId}
          RETURNING id, name, lines, created_at, updated_at`,
      );
      return row ? savedList(row) : null;
    },

    async deleteList(userId, id) {
      const rows = await query((sql) =>
        sql`DELETE FROM saved_lists WHERE id = ${id} AND user_id = ${userId} RETURNING id`,
      );
      return rows.length > 0;
    },
  };
}

/* -------------------------------------------------------------------------------------------- */
/* Memory (tests and a database-less preview)                                                    */
/* -------------------------------------------------------------------------------------------- */

export function memoryAccountStore(): AccountStore {
  type Recorded = { account: Account; password_hash: string | null; google_sub: string | null };
  const users = new Map<string, Recorded>();
  const byEmail = new Map<string, string>();
  const byGoogle = new Map<string, string>();
  const sessions = new Map<string, { userId: string; expiresAt: number }>();
  const preferences = new Map<string, Preferences>();
  const lists = new Map<string, SavedList[]>();

  return {
    async createUser(input) {
      if (byEmail.has(input.email)) throw new AccountExistsError();
      const now = new Date().toISOString();
      const account: Account = { id: crypto.randomUUID(), email: input.email, name: input.name, created_at: now };
      users.set(account.id, { account, password_hash: input.password_hash, google_sub: input.google_sub });
      byEmail.set(input.email, account.id);
      if (input.google_sub) byGoogle.set(input.google_sub, account.id);
      return account;
    },
    async userByEmail(email) {
      const id = byEmail.get(email);
      const user = id ? users.get(id) : undefined;
      return user ? { account: user.account, password_hash: user.password_hash } : null;
    },
    async userByGoogleSub(sub) {
      const id = byGoogle.get(sub);
      return (id && users.get(id)?.account) || null;
    },
    async linkGoogle(userId, sub) {
      const user = users.get(userId);
      if (!user) throw new Error("Account not found");
      user.google_sub = sub;
      byGoogle.set(sub, userId);
      return user.account;
    },
    async createSession(tokenHash, userId, expiresAt) {
      sessions.set(tokenHash, { userId, expiresAt: expiresAt.getTime() });
    },
    async sessionUser(tokenHash) {
      const session = sessions.get(tokenHash);
      if (!session || session.expiresAt <= Date.now()) {
        sessions.delete(tokenHash);
        return null;
      }
      return users.get(session.userId)?.account || null;
    },
    async deleteSession(tokenHash) {
      sessions.delete(tokenHash);
    },
    async preferences(userId) {
      return preferences.get(userId) ?? { ...DEFAULT_PREFERENCES };
    },
    async savePreferences(userId, next) {
      preferences.set(userId, next);
      return next;
    },
    async lists(userId) {
      return [...(lists.get(userId) ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    },
    async createList(userId, name, lines) {
      const now = new Date().toISOString();
      const list: SavedList = { id: crypto.randomUUID(), name, lines, created_at: now, updated_at: now };
      lists.set(userId, [...(lists.get(userId) ?? []), list]);
      return list;
    },
    async updateList(userId, id, name, lines) {
      const owned = lists.get(userId) ?? [];
      const current = owned.find((list) => list.id === id);
      if (!current) return null;
      const updated: SavedList = { ...current, name, lines, updated_at: new Date().toISOString() };
      lists.set(
        userId,
        owned.map((list) => (list.id === id ? updated : list)),
      );
      return updated;
    },
    async deleteList(userId, id) {
      const owned = lists.get(userId) ?? [];
      const kept = owned.filter((list) => list.id !== id);
      lists.set(userId, kept);
      return kept.length !== owned.length;
    },
  };
}

/* -------------------------------------------------------------------------------------------- */
/* HTTP routes                                                                                   */
/* -------------------------------------------------------------------------------------------- */

export type AccountBindings = {
  HYPERDRIVE?: { connectionString: string };
  /** A writable Hyperdrive config for the account tables; falls back to HYPERDRIVE in development. */
  ACCOUNTS_HYPERDRIVE?: { connectionString: string };
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  /** Public origin for the Google redirect (defaults to the request's own origin). */
  ACCOUNTS_PUBLIC_URL?: string;
};

export type AccountDeps = {
  store: (env: AccountBindings) => AccountStore;
  fetchImpl?: typeof fetch;
  now?: () => Date;
};

const isSecure = (c: Context) => new URL(c.req.url).protocol === "https:";
const originOf = (c: Context, env: AccountBindings) => env.ACCOUNTS_PUBLIC_URL?.replace(/\/+$/, "") || new URL(c.req.url).origin;

/** A state-changing request must come from the site itself (the session cookie is SameSite=Lax as well). */
function sameOrigin(c: Context, env: AccountBindings): boolean {
  const origin = c.req.header("Origin");
  if (!origin) return true; // same-origin form posts and non-browser clients (curl) omit it
  try {
    const given = new URL(origin).origin;
    if (given === new URL(c.req.url).origin) return true;
    // Behind a proxy whose request origin is not the public one, the configured public URL is the site.
    return Boolean(env.ACCOUNTS_PUBLIC_URL) && given === new URL(env.ACCOUNTS_PUBLIC_URL!).origin;
  } catch {
    return false;
  }
}

function sessionCookie(c: Context, token: string, maxAge: number) {
  setCookie(c, SESSION_COOKIE, token, {
    path: "/",
    httpOnly: true,
    secure: isSecure(c),
    sameSite: "Lax",
    maxAge,
  });
}

async function currentAccount(c: Context, store: AccountStore): Promise<Account | null> {
  const token = getCookie(c, SESSION_COOKIE);
  return token ? store.sessionUser(await hashToken(token)) : null;
}

async function startSession(c: Context, store: AccountStore, userId: string, now: Date) {
  const token = randomToken();
  const expiresAt = new Date(now.getTime() + SESSION_DAYS * 86_400_000);
  await store.createSession(await hashToken(token), userId, expiresAt);
  sessionCookie(c, token, SESSION_DAYS * 86_400);
}

/** A signed-in request, or a 401 response. */
async function requireAccount(c: Context, store: AccountStore) {
  const account = await currentAccount(c, store);
  if (!account) return { account: null, response: c.json({ error: "Entre na sua conta para continuar." }, 401) };
  return { account, response: null };
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function accountRoutes(deps: AccountDeps): Hono<{ Bindings: AccountBindings }> {
  const app = new Hono<{ Bindings: AccountBindings }>();
  const fetchImpl = deps.fetchImpl ?? fetch;
  const now = deps.now ?? (() => new Date());
  const store = (c: Context) => deps.store(c.env as AccountBindings);
  // A small per-isolate brake on password guessing; a real deployment would use a shared store.
  const attempts = new Map<string, { count: number; resetAt: number }>();

  // Account answers are per-person: no browser, proxy or CDN may keep a copy.
  app.use("/auth/*", async (c, next) => {
    await next();
    c.header("Cache-Control", "no-store");
  });
  app.use("/account/*", async (c, next) => {
    await next();
    c.header("Cache-Control", "no-store");
  });

  function throttled(c: Context, email: string): boolean {
    const ip = c.req.header("CF-Connecting-IP") ?? c.req.header("X-Forwarded-For")?.split(",")[0]?.trim() ?? "local";
    const key = `${ip}|${email}`;
    const entry = attempts.get(key);
    if (!entry || entry.resetAt <= Date.now()) return false;
    return entry.count >= 10;
  }

  function countFailure(c: Context, email: string) {
    const ip = c.req.header("CF-Connecting-IP") ?? c.req.header("X-Forwarded-For")?.split(",")[0]?.trim() ?? "local";
    const key = `${ip}|${email}`;
    const entry = attempts.get(key);
    if (!entry || entry.resetAt <= Date.now()) {
      attempts.set(key, { count: 1, resetAt: Date.now() + 15 * 60_000 });
    } else {
      entry.count += 1;
    }
  }

  app.post("/auth/register", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const body = (await c.req.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body || typeof body !== "object") return c.json({ error: "Envie os dados em JSON." }, 400);
    const email = normalizeEmail(body.email);
    const problem = emailProblem(email) || passwordProblem(body.password);
    if (problem) return c.json({ error: problem }, 400);
    const name = cleanName(body.name);
    if (name === undefined) return c.json({ error: `O nome pode ter no máximo ${MAX_NAME} caracteres.` }, 400);

    let account: Account;
    try {
      account = await store(c).createUser({
        email,
        password_hash: await hashPassword(body.password as string),
        name,
        google_sub: null,
      });
    } catch (error) {
      if (error instanceof AccountExistsError)
        return c.json({ error: "Já existe uma conta com este e-mail. Entre com sua senha." }, 409);
      throw error;
    }
    await startSession(c, store(c), account.id, now());
    return c.json({ user: account, preferences: DEFAULT_PREFERENCES }, 201);
  });

  app.post("/auth/login", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const body = (await c.req.json().catch(() => null)) as Record<string, unknown> | null;
    const email = normalizeEmail(body?.email);
    const password = typeof body?.password === "string" ? body.password : "";
    if (!email || !password) return c.json({ error: "Informe o e-mail e a senha." }, 400);
    if (throttled(c, email))
      return c.json({ error: "Muitas tentativas. Espere alguns minutos antes de tentar de novo." }, 429);

    const found = await store(c).userByEmail(email);
    const valid = found ? await verifyPassword(password, found.password_hash) : false;
    if (!found || !valid) {
      countFailure(c, email);
      // The same answer for an unknown e-mail and a wrong password: nothing to enumerate.
      return c.json({ error: "E-mail ou senha incorretos." }, 401);
    }
    await startSession(c, store(c), found.account.id, now());
    return c.json({ user: found.account, preferences: await store(c).preferences(found.account.id) });
  });

  app.post("/auth/logout", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const token = getCookie(c, SESSION_COOKIE);
    if (token) await store(c).deleteSession(await hashToken(token));
    deleteCookie(c, SESSION_COOKIE, { path: "/" });
    return c.json({ ok: true });
  });

  app.get("/auth/me", async (c) => {
    const account = await currentAccount(c, store(c));
    return c.json({
      user: account,
      preferences: account ? await store(c).preferences(account.id) : null,
      // The UI hides the Google button when this deployment has no Google credentials.
      google: Boolean(c.env.GOOGLE_CLIENT_ID && c.env.GOOGLE_CLIENT_SECRET),
    });
  });

  app.get("/auth/google/start", (c) => {
    if (!c.env.GOOGLE_CLIENT_ID || !c.env.GOOGLE_CLIENT_SECRET)
      return c.json({ error: "Entrar com Google não está configurado neste servidor." }, 503);
    const state = randomToken(24);
    setCookie(c, OAUTH_COOKIE, state, {
      path: "/api/auth/google",
      httpOnly: true,
      secure: isSecure(c),
      sameSite: "Lax",
      maxAge: 600,
    });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
    url.searchParams.set("redirect_uri", new URL("/api/auth/google/callback", originOf(c, c.env)).toString());
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", "openid email profile");
    url.searchParams.set("state", state);
    url.searchParams.set("prompt", "select_account");
    return c.redirect(url.toString(), 302);
  });

  app.get("/auth/google/callback", async (c) => {
    const base = originOf(c, c.env);
    const failure = (reason: string) => {
      const url = new URL("/conta", base);
      url.searchParams.set("erro", reason);
      return c.redirect(url.toString(), 302);
    };
    const state = c.req.query("state") ?? "";
    const expected = getCookie(c, OAUTH_COOKIE);
    deleteCookie(c, OAUTH_COOKIE, { path: "/api/auth/google" });
    if (!c.env.GOOGLE_CLIENT_ID || !c.env.GOOGLE_CLIENT_SECRET) return failure("google-indisponivel");
    if (!state || !expected || state !== expected) return failure("google-estado");
    const code = c.req.query("code");
    if (!code) return failure("google-cancelado");

    let claims: Record<string, unknown> | null = null;
    try {
      const response = await fetchImpl("https://oauth2.googleapis.com/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          code,
          client_id: c.env.GOOGLE_CLIENT_ID,
          client_secret: c.env.GOOGLE_CLIENT_SECRET,
          redirect_uri: new URL("/api/auth/google/callback", base).toString(),
          grant_type: "authorization_code",
        }),
      });
      if (!response.ok) return failure("google-token");
      const tokens = (await response.json()) as { id_token?: unknown };
      claims = typeof tokens.id_token === "string" ? decodeJwtPayload(tokens.id_token) : null;
    } catch {
      return failure("google-token");
    }

    const issuer = claims?.iss;
    const audience = claims?.aud;
    const expires = typeof claims?.exp === "number" ? claims.exp * 1000 : 0;
    const sub = typeof claims?.sub === "string" ? claims.sub : "";
    const email = normalizeEmail(claims?.email);
    const verified = claims?.email_verified === true || claims?.email_verified === "true";
    const valid =
      (issuer === "accounts.google.com" || issuer === "https://accounts.google.com") &&
      audience === c.env.GOOGLE_CLIENT_ID &&
      expires > now().getTime() &&
      sub.length > 0 &&
      !emailProblem(email) &&
      verified;
    // The token came straight from Google over TLS, so its claims are trusted once they match this app.
    if (!valid) return failure("google-token");

    let account = await store(c).userByGoogleSub(sub);
    if (!account) {
      const existing = await store(c).userByEmail(email);
      if (existing) {
        account = await store(c).linkGoogle(existing.account.id, sub);
      } else {
        try {
          account = await store(c).createUser({
            email,
            password_hash: null,
            name: cleanName(claims?.name) ?? null,
            google_sub: sub,
          });
        } catch (error) {
          if (!(error instanceof AccountExistsError)) throw error;
          const raced = await store(c).userByEmail(email);
          if (!raced) return failure("google-conta");
          account = await store(c).linkGoogle(raced.account.id, sub);
        }
      }
    }
    await startSession(c, store(c), account.id, now());
    return c.redirect(new URL("/conta?entrou=google", base).toString(), 302);
  });

  app.get("/account/preferences", async (c) => {
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    return c.json({ preferences: await store(c).preferences(account.id) });
  });

  app.put("/account/preferences", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    const preferences = sanitizePreferences(await c.req.json().catch(() => null));
    if (!preferences) return c.json({ error: "Preferências inválidas." }, 400);
    return c.json({ preferences: await store(c).savePreferences(account.id, preferences) });
  });

  app.get("/account/lists", async (c) => {
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    return c.json({ lists: await store(c).lists(account.id) });
  });

  app.post("/account/lists", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    const body = (await c.req.json().catch(() => null)) as Record<string, unknown> | null;
    const name = cleanListName(body?.name);
    const lines = sanitizeLines(body?.lines);
    if (!name) return c.json({ error: `Dê um nome à lista (até ${MAX_LIST_NAME} caracteres).` }, 400);
    if (!lines) return c.json({ error: "A lista enviada é inválida." }, 400);
    if ((await store(c).lists(account.id)).length >= MAX_LISTS)
      return c.json({ error: `Você já tem ${MAX_LISTS} listas salvas. Exclua uma para salvar outra.` }, 409);
    return c.json({ list: await store(c).createList(account.id, name, lines) }, 201);
  });

  app.put("/account/lists/:id", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    const body = (await c.req.json().catch(() => null)) as Record<string, unknown> | null;
    const name = cleanListName(body?.name);
    const lines = sanitizeLines(body?.lines);
    if (!name) return c.json({ error: `Dê um nome à lista (até ${MAX_LIST_NAME} caracteres).` }, 400);
    if (!lines) return c.json({ error: "A lista enviada é inválida." }, 400);
    const list = await store(c).updateList(account.id, c.req.param("id"), name, lines);
    if (!list) return c.json({ error: "Lista não encontrada." }, 404);
    return c.json({ list });
  });

  app.delete("/account/lists/:id", async (c) => {
    if (!sameOrigin(c, c.env)) return c.json({ error: "Origem inválida." }, 403);
    const { account, response } = await requireAccount(c, store(c));
    if (!account) return response;
    const deleted = await store(c).deleteList(account.id, c.req.param("id"));
    if (!deleted) return c.json({ error: "Lista não encontrada." }, 404);
    return c.json({ ok: true });
  });

  return app;
}
