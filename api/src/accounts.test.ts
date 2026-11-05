import { describe, expect, it, vi } from "vitest";
import { createApp } from "./app";
import { hashPassword, memoryAccountStore, verifyPassword, type AccountStore } from "./accounts";
import type { SnapshotStore } from "./store";

const env = { HYPERDRIVE: { connectionString: "postgres://unused" } };
const snapshots: SnapshotStore = {
  latestMeta: async () => null,
  latest: async () => null,
  priceHistory: async () => [],
};

function makeApp(options: {
  fetchImpl?: typeof fetch;
  accounts?: AccountStore;
  env?: Record<string, unknown>;
  now?: () => Date;
} = {}) {
  const accounts = options.accounts ?? memoryAccountStore();
  const app = createApp({
    store: () => snapshots,
    accounts: () => accounts,
    fetchImpl: options.fetchImpl,
    now: options.now,
  });
  return { app, accounts, env: { ...env, ...options.env } };
}

type App = ReturnType<typeof makeApp>;

const cookies = (response: Response) =>
  response.headers.getSetCookie?.() ?? (response.headers.get("Set-Cookie") ?? "").split(/,(?=\s*\w+=)/);
const cookie = (response: Response, name = "med_session") =>
  (cookies(response).find((value) => value.startsWith(`${name}=`)) ?? "").split(";")[0];

/** An unsigned JWT-shaped token: the API only reads its payload (the token comes from Google over TLS). */
const idToken = (claims: Record<string, unknown>) =>
  ["header", btoa(JSON.stringify(claims)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""), "signature"].join(".");

const post = (
  harness: App,
  path: string,
  body: unknown,
  session?: string,
  headers: Record<string, string> = {},
) =>
  harness.app.request(
    path,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Cookie: session } : {}),
        ...headers,
      },
      body: JSON.stringify(body),
    },
    harness.env,
  );

const put = (harness: App, path: string, body: unknown, session: string) =>
  harness.app.request(
    path,
    { method: "PUT", headers: { "Content-Type": "application/json", Cookie: session }, body: JSON.stringify(body) },
    harness.env,
  );

const me = (harness: App, session?: string) =>
  harness.app.request("/api/auth/me", { headers: session ? { Cookie: session } : {} }, harness.env);

const register = (harness: App, email = "ana@example.com", password = "segredo123", name?: string) =>
  post(harness, "/api/auth/register", { email, password, name });

describe("POST /api/auth/register", () => {
  it("creates the account, signs it in and starts from the default preferences", async () => {
    const harness = makeApp();
    const response = await register(harness, " Ana@Example.com ", "segredo123", "Ana");
    expect(response.status).toBe(201);
    expect(response.headers.get("Set-Cookie")).toContain("HttpOnly");
    expect(response.headers.get("Set-Cookie")).toContain("SameSite=Lax");
    const body = (await response.json()) as { user: { email: string; name: string } };
    expect(body.user.email).toBe("ana@example.com"); // normalised
    expect(body.user.name).toBe("Ana");

    const session = await me(harness, cookie(response));
    const data = (await session.json()) as { user: { email: string }; preferences: { region: string; location: null } };
    expect(data.user.email).toBe("ana@example.com");
    expect(data.preferences).toEqual({ region: "Fortaleza", location: null });
  });

  it.each([
    [{ email: "not-an-email", password: "segredo123" }],
    [{ email: "ana@example.com", password: "curta" }],
    [{ email: "ana@example.com" }],
    [{ password: "segredo123" }],
  ])("refuses %j with a message", async (body) => {
    const harness = makeApp();
    const response = await post(harness, "/api/auth/register", body);
    expect(response.status).toBe(400);
    expect((await response.json()) as { error: string }).toHaveProperty("error");
  });

  it("refuses a second account with the same e-mail", async () => {
    const harness = makeApp();
    await register(harness);
    const again = await register(harness, "ANA@example.com");
    expect(again.status).toBe(409);
    expect(((await again.json()) as { error: string }).error).toContain("Já existe uma conta");
  });

  it("refuses a state-changing request from another origin", async () => {
    const harness = makeApp();
    const response = await post(harness, "/api/auth/register", { email: "a@b.co", password: "segredo123" }, undefined, {
      Origin: "https://evil.example",
    });
    expect(response.status).toBe(403);
  });

  it("accepts the public URL when a proxy hides the request origin", async () => {
    const harness = makeApp({ env: { ACCOUNTS_PUBLIC_URL: "https://mercadoemdia.example" } });
    const response = await post(harness, "/api/auth/register", { email: "a@b.co", password: "segredo123" }, undefined, {
      Origin: "https://mercadoemdia.example",
    });
    expect(response.status).toBe(201);
  });

  it("answers a body that is not JSON without crashing", async () => {
    const harness = makeApp();
    const response = await harness.app.request(
      "/api/auth/register",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "not json" },
      harness.env,
    );
    expect(response.status).toBe(400);
  });
});

describe("POST /api/auth/login", () => {
  it("signs in with the right password and refuses the wrong one", async () => {
    const harness = makeApp();
    await register(harness);
    const wrong = await post(harness, "/api/auth/login", { email: "ana@example.com", password: "errada123" });
    expect(wrong.status).toBe(401);
    expect(((await wrong.json()) as { error: string }).error).toBe("E-mail ou senha incorretos.");

    const right = await post(harness, "/api/auth/login", { email: "ana@example.com", password: "segredo123" });
    expect(right.status).toBe(200);
    const data = (await (await me(harness, cookie(right))).json()) as { user: { email: string } };
    expect(data.user.email).toBe("ana@example.com");
  });

  it("gives the same answer for an unknown e-mail as for a wrong password", async () => {
    const harness = makeApp();
    const response = await post(harness, "/api/auth/login", { email: "ninguem@example.com", password: "segredo123" });
    expect(response.status).toBe(401);
    expect(((await response.json()) as { error: string }).error).toBe("E-mail ou senha incorretos.");
  });

  it("refuses a Google-only account's e-mail as a password login", async () => {
    const accounts = memoryAccountStore();
    const harness = makeApp({ accounts });
    await accounts.createUser({ email: "g@example.com", password_hash: null, name: null, google_sub: "sub-1" });
    const response = await post(harness, "/api/auth/login", { email: "g@example.com", password: "segredo123" });
    expect(response.status).toBe(401);
  });
});

describe("session", () => {
  it("is null before signing in", async () => {
    const harness = makeApp();
    const response = await me(harness);
    expect(await response.json()).toMatchObject({ user: null, preferences: null, google: false });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });

  it("ends on logout and cannot be reused", async () => {
    const harness = makeApp();
    const created = await register(harness);
    const session = cookie(created);
    expect(((await (await me(harness, session)).json()) as { user: unknown }).user).not.toBeNull();
    const logout = await harness.app.request("/api/auth/logout", { method: "POST", headers: { Cookie: session } }, harness.env);
    expect(logout.status).toBe(200);
    expect(cookies(logout).some((value) => value.startsWith("med_session=;"))).toBe(true);
    // The fake store is shared, so a stale cookie no longer resolves to an account.
    expect(((await (await me(harness, session)).json()) as { user: unknown }).user).toBeNull();
  });

  it("reports whether Google sign-in is configured", async () => {
    const harness = makeApp({ env: { GOOGLE_CLIENT_ID: "id", GOOGLE_CLIENT_SECRET: "secret" } });
    expect((await (await me(harness)).json()) as { google: boolean }).toMatchObject({ google: true });
  });
});

describe("/api/account/preferences", () => {
  it("needs a session", async () => {
    const harness = makeApp();
    expect((await harness.app.request("/api/account/preferences", {}, harness.env)).status).toBe(401);
  });

  it("saves and returns the preferred place, and can clear it", async () => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    const location = { label: "Casa · Rua A, 10 · Meireles", latitude: -3.72, longitude: -38.5, radius_km: 5 };
    const saved = await put(harness, "/api/account/preferences", { region: "Fortaleza", location }, session);
    expect(saved.status).toBe(200);
    expect((await saved.json()) as { preferences: unknown }).toEqual({ preferences: { region: "Fortaleza", location } });

    const read = await harness.app.request("/api/account/preferences", { headers: { Cookie: session } }, harness.env);
    expect((await read.json()) as { preferences: unknown }).toEqual({ preferences: { region: "Fortaleza", location } });

    const cleared = await put(harness, "/api/account/preferences", { region: "Fortaleza", location: null }, session);
    expect(((await cleared.json()) as { preferences: { location: unknown } }).preferences.location).toBeNull();
  });

  it.each([
    { location: { label: "", latitude: -3.7, longitude: -38.5, radius_km: 5 } },
    { location: { label: "Casa", latitude: 91, longitude: -38.5, radius_km: 5 } },
    { location: { label: "Casa", latitude: -3.7, longitude: -38.5, radius_km: 2.5 } },
    { location: { label: "Casa", latitude: -3.7, longitude: -38.5, radius_km: 80 } },
  ])("refuses a malformed place: %j", async (body) => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    expect((await put(harness, "/api/account/preferences", body, session)).status).toBe(400);
  });
});

describe("/api/account/lists", () => {
  const lines = [
    { product_id: "arroz-5kg", name: "Arroz 5 kg", quantity: 2, checked: false },
    { product_id: "feijao-1kg", name: "Feijão 1 kg", quantity: 1, checked: true },
  ];

  it("keeps a list for the signed-in account only", async () => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    const created = await post(harness, "/api/account/lists", { name: "Mercado da semana", lines }, session);
    expect(created.status).toBe(201);
    const list = ((await created.json()) as { list: { id: string; name: string; lines: unknown } }).list;
    expect(list.name).toBe("Mercado da semana");
    expect(list.lines).toEqual(lines);

    const all = await harness.app.request("/api/account/lists", { headers: { Cookie: session } }, harness.env);
    expect(((await all.json()) as { lists: unknown[] }).lists).toHaveLength(1);

    const other = cookie(await register(harness, "outra@example.com"));
    const theirs = await harness.app.request("/api/account/lists", { headers: { Cookie: other } }, harness.env);
    expect(((await theirs.json()) as { lists: unknown[] }).lists).toEqual([]);
    const steal = await put(harness, `/api/account/lists/${list.id}`, { name: "x", lines }, other);
    expect(steal.status).toBe(404);
  });

  it("updates and deletes an owned list", async () => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    const created = await post(harness, "/api/account/lists", { name: "Antiga", lines }, session);
    const { id } = ((await created.json()) as { list: { id: string } }).list;

    const updated = await put(harness, `/api/account/lists/${id}`, { name: "Nova", lines: [] }, session);
    expect(updated.status).toBe(200);
    expect(((await updated.json()) as { list: { name: string; lines: unknown[] } }).list).toEqual(
      expect.objectContaining({ name: "Nova", lines: [] }),
    );

    expect((await harness.app.request(`/api/account/lists/${id}`, { method: "DELETE", headers: { Cookie: session } }, harness.env)).status).toBe(200);
    const all = await harness.app.request("/api/account/lists", { headers: { Cookie: session } }, harness.env);
    expect(((await all.json()) as { lists: unknown[] }).lists).toEqual([]);
    expect((await harness.app.request(`/api/account/lists/${id}`, { method: "DELETE", headers: { Cookie: session } }, harness.env)).status).toBe(404);
  });

  it.each([
    { name: "", lines },
    { name: "x".repeat(81), lines },
    { name: "Lista", lines: [{ product_id: "", name: "x", quantity: 1, checked: false }] },
    { name: "Lista", lines: [{ product_id: "a", name: "x", quantity: 0, checked: false }] },
    { name: "Lista", lines: [{ product_id: "a", name: "x", quantity: 1.5, checked: false }] },
    { name: "Lista", lines: [{ product_id: "a", name: "x", quantity: 1, checked: false }, 42] },
    { name: "Lista", lines: "não é lista" },
  ])("refuses a malformed list: %j", async (body) => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    expect((await post(harness, "/api/account/lists", body, session)).status).toBe(400);
  });

  it("refuses a new list past the per-account limit", async () => {
    const harness = makeApp();
    const session = cookie(await register(harness));
    for (let i = 0; i < 20; i++) {
      expect((await post(harness, "/api/account/lists", { name: `Lista ${i}`, lines: [] }, session)).status).toBe(201);
    }
    expect((await post(harness, "/api/account/lists", { name: "Uma a mais", lines: [] }, session)).status).toBe(409);
  });

  it("needs a session for every operation", async () => {
    const harness = makeApp();
    expect((await post(harness, "/api/account/lists", { name: "x", lines: [] })).status).toBe(401);
    expect((await harness.app.request("/api/account/lists", {}, harness.env)).status).toBe(401);
    expect((await put(harness, "/api/account/lists/x", { name: "x", lines: [] }, "med_session=nope")).status).toBe(401);
    expect((await harness.app.request("/api/account/lists/x", { method: "DELETE" }, harness.env)).status).toBe(401);
  });
});

describe("Google sign-in", () => {
  const googleEnv = { GOOGLE_CLIENT_ID: "client-id", GOOGLE_CLIENT_SECRET: "client-secret" };

  it("says so when the deployment has no Google credentials", async () => {
    const harness = makeApp();
    expect((await harness.app.request("/api/auth/google/start", {}, harness.env)).status).toBe(503);
  });

  it("redirects to Google with its own state, and refuses a mismatched callback", async () => {
    const harness = makeApp({ env: googleEnv });
    const start = await harness.app.request("/api/auth/google/start", {}, harness.env);
    expect(start.status).toBe(302);
    const target = new URL(start.headers.get("Location") ?? "");
    expect(target.origin + target.pathname).toBe("https://accounts.google.com/o/oauth2/v2/auth");
    expect(target.searchParams.get("client_id")).toBe("client-id");
    expect(target.searchParams.get("scope")).toContain("email");
    expect(target.searchParams.get("redirect_uri")).toBe("http://localhost/api/auth/google/callback");
    expect(cookie(start, "med_oauth_state")).toContain("med_oauth_state=");

    const stateCookie = cookie(start, "med_oauth_state");
    const bad = await harness.app.request(
      `/api/auth/google/callback?code=abc&state=wrong`,
      { headers: { Cookie: stateCookie } },
      harness.env,
    );
    expect(bad.status).toBe(302);
    expect(bad.headers.get("Location")).toContain("/conta?erro=google-estado");
  });

  it("creates an account from the verified Google profile", async () => {
    const claims = {
      iss: "https://accounts.google.com",
      aud: "client-id",
      exp: Math.floor(Date.now() / 1000) + 300,
      sub: "google-sub-1",
      email: "gmail@example.com",
      email_verified: true,
      name: "Gmail da Silva",
    };
    const spy = vi.fn(async () => Response.json({ id_token: idToken(claims) }));
    const fetchImpl = spy as unknown as typeof fetch;
    const harness = makeApp({ env: googleEnv, fetchImpl });
    const start = await harness.app.request("/api/auth/google/start", {}, harness.env);
    const state = new URL(start.headers.get("Location") ?? "").searchParams.get("state");
    const session = cookie(start, "med_oauth_state");

    const callback = await harness.app.request(
      `/api/auth/google/callback?code=abc&state=${state}`,
      { headers: { Cookie: session } },
      harness.env,
    );
    expect(callback.status).toBe(302);
    expect(callback.headers.get("Location")).toContain("/conta?entrou=google");
    const signedIn = cookie(callback);
    expect(signedIn).toContain("med_session=");

    const profile = (await (await me(harness, signedIn)).json()) as {
      user: { email: string; name: string };
    };
    expect(profile.user).toMatchObject({ email: "gmail@example.com", name: "Gmail da Silva" });

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://oauth2.googleapis.com/token");
    expect((init.body as URLSearchParams).get("grant_type")).toBe("authorization_code");
  });

  it("links Google to an existing e-mail account instead of duplicating it", async () => {
    const fetchImpl = vi.fn(async () =>
      Response.json({
        id_token: idToken({
          iss: "accounts.google.com",
          aud: "client-id",
          exp: Math.floor(Date.now() / 1000) + 300,
          sub: "google-sub-2",
          email: "ana@example.com",
          email_verified: true,
        }),
      }),
    ) as unknown as typeof fetch;
    const harness = makeApp({ env: googleEnv, fetchImpl });
    await register(harness, "ana@example.com");

    const start = await harness.app.request("/api/auth/google/start", {}, harness.env);
    const state = new URL(start.headers.get("Location") ?? "").searchParams.get("state");
    const callback = await harness.app.request(
      `/api/auth/google/callback?code=abc&state=${state}`,
      { headers: { Cookie: cookie(start, "med_oauth_state") } },
      harness.env,
    );
    const profile = (await (await me(harness, cookie(callback))).json()) as { user: { email: string } };
    expect(profile.user.email).toBe("ana@example.com");
  });

  it("refuses a token for another audience or an unverified e-mail", async () => {
    for (const claims of [
      { iss: "accounts.google.com", aud: "other-client", exp: Math.floor(Date.now() / 1000) + 300, sub: "s", email: "a@b.co", email_verified: true },
      { iss: "accounts.google.com", aud: "client-id", exp: Math.floor(Date.now() / 1000) + 300, sub: "s", email: "a@b.co", email_verified: false },
    ]) {
      const fetchImpl = vi.fn(async () =>
        Response.json({
          id_token: idToken(claims),
        }),
      ) as unknown as typeof fetch;
      const harness = makeApp({ env: googleEnv, fetchImpl });
      const start = await harness.app.request("/api/auth/google/start", {}, harness.env);
      const state = new URL(start.headers.get("Location") ?? "").searchParams.get("state");
      const callback = await harness.app.request(
        `/api/auth/google/callback?code=abc&state=${state}`,
        { headers: { Cookie: cookie(start, "med_oauth_state") } },
        harness.env,
      );
      expect(callback.headers.get("Location")).toContain("/conta?erro=google-token");
    }
  });
});

describe("password hashing", () => {
  it("never stores the password and accepts it back", async () => {
    const hash = await hashPassword("segredo123");
    expect(hash).not.toContain("segredo123");
    expect(hash.startsWith("pbkdf2-sha256$")).toBe(true);
    expect(await verifyPassword("segredo123", hash)).toBe(true);
    expect(await verifyPassword("outra-senha", hash)).toBe(false);
    expect(await verifyPassword("segredo123", null)).toBe(false);
    expect(await verifyPassword("segredo123", "lixo")).toBe(false);
  });
});
