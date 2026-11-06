import { Hono } from "hono";
import { accountRoutes, postgresAccountStore, type AccountBindings, type AccountStore } from "./accounts";
import {
  AddressSearchError,
  MAX_QUERY,
  MIN_QUERY,
  normalize,
  reverseAddress,
  searchAddresses,
} from "./geocoding";
import { DEFAULT_LIMIT, limitOf, MAX_QUERY as MAX_SEARCH, MIN_QUERY as MIN_SEARCH, wordsOf } from "./search";
import type { Snapshot, SnapshotStore } from "./store";

export type Bindings = {
  HYPERDRIVE: { connectionString: string };
  /** Optional writable connection for accounts; without it the read connection is used (local dev only). */
  ACCOUNTS_HYPERDRIVE?: { connectionString: string };
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  ACCOUNTS_PUBLIC_URL?: string;
  /** Where the receipt OCR runs (the VPS, behind Caddy), and the secret it expects. Without both: 501. */
  OCR_URL?: string;
  OCR_SECRET?: string;
  /** Cloudflare's rate-limit binding (see wrangler.jsonc); absent in tests and local development. */
  RECEIPT_LIMITER?: { limit(options: { key: string }): Promise<{ success: boolean }> };
};

type Deps = {
  store: (env: Bindings) => SnapshotStore;
  /** Account storage; defaults to Postgres through the same (or the ACCOUNTS_) connection. */
  accounts?: (env: AccountBindings) => AccountStore;
  fetchImpl?: typeof fetch;
  now?: () => Date;
};

// Data changes when a scrape is published (hours apart): browsers reuse it for a minute and may show
// a stale copy for five more while they refresh it; revalidating with the etag costs almost nothing.
const CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300";

// Price history grows by a few rows a day per product, so a few minutes' staleness is invisible.
const HISTORY_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=600";
export const HISTORY_MAX_KEYS = 30;

// A search result changes only when a scrape is published, so a minute of reuse is invisible.
const SEARCH_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300";
const PRICE_KEY = /^[0-9a-f]{32}$/;

// The photo may be 10 MB (the VPS refuses more); the form around it adds a little.
const RECEIPT_UPLOAD_MAX_BYTES = 10 * 1024 * 1024 + 64 * 1024;
// The VPS reads a receipt in 2-6 s normally; its own provider retries can stretch that.
const RECEIPT_TIMEOUT_MS = 120_000;

export function createApp({ store, accounts, fetchImpl = fetch, now }: Deps) {
  const app = new Hono<{ Bindings: Bindings }>();
  const accountStore =
    accounts ??
    ((env: AccountBindings) =>
      postgresAccountStore((env.ACCOUNTS_HYPERDRIVE ?? env.HYPERDRIVE)!.connectionString));
  // Payloads are large and change rarely, so each isolate keeps the newest one and only re-reads it
  // from the database when the etag changes.
  let cached: Snapshot | null = null;

  app.get("/api/health", (c) => c.json({ ok: true }));

  app.get("/api/public", async (c) => {
    const source = store(c.env);
    const meta = await source.latestMeta();
    if (!meta) {
      return c.json({ error: "Os dados ainda não foram publicados." }, 503, { "Cache-Control": "no-store" });
    }
    const etag = `"${meta.etag}"`;
    const headers = { ETag: etag, "Cache-Control": CACHE_CONTROL };
    const sent = c.req.header("If-None-Match");
    if (sent && sent.split(",").some((v) => v.trim().replace(/^W\//, "") === etag)) {
      return new Response(null, { status: 304, headers });
    }
    if (cached?.etag !== meta.etag) {
      const latest = await source.latest();
      if (!latest) return c.json({ error: "Os dados ainda não foram publicados." }, 503, { "Cache-Control": "no-store" });
      cached = latest;
    }
    return new Response(cached.payload, {
      headers: {
        ...headers,
        ETag: `"${cached.etag}"`,
        "Content-Type": "application/json; charset=utf-8",
      },
    });
  });

  // How prices moved: ?keys=<price_key>,<price_key> (the offers' price_key) answered as
  // {"history": {key: {chain: [[observed_at, price_cents], ...]}}}. The local Flask API serves the same shape.
  app.get("/api/price-history", async (c) => {
    const keys = (c.req.query("keys") ?? "").split(",").filter(Boolean);
    if (!keys.length || keys.length > HISTORY_MAX_KEYS || !keys.every((k) => PRICE_KEY.test(k))) {
      return c.json({ error: `Informe de 1 a ${HISTORY_MAX_KEYS} chaves de preço.` }, 400);
    }
    const history: Record<string, Record<string, [string, number][]>> = {};
    for (const point of await store(c.env).priceHistory([...new Set(keys)])) {
      ((history[point.key] ??= {})[point.store] ??= []).push([point.observedAt, point.priceCents]);
    }
    return c.json({ history }, 200, { "Cache-Control": HISTORY_CACHE_CONTROL });
  });

  // The whole catalogue, not only what the snapshot carries (the snapshot is capped per chain): ?q=arroz&limit=40,
  // answered from the cloud database's products and current_prices. The Flask API serves the same shape.
  app.get("/api/search", async (c) => {
    const words = wordsOf(c.req.query("q") ?? "");
    if (!words.length) {
      return c.json({ error: `Digite de ${MIN_SEARCH} a ${MAX_SEARCH} caracteres para buscar.` }, 400);
    }
    try {
      const body = await store(c.env).searchCatalogue(words, limitOf(c.req.query("limit") ?? String(DEFAULT_LIMIT)));
      return c.json(body, 200, { "Cache-Control": SEARCH_CACHE_CONTROL });
    } catch (error) {
      // Before the first publish that writes current_prices, or before api_reader may read it (see
      // scraping/db/readonly_role.sql), the search is simply not there yet - say so rather than a generic failure.
      const code = (error as { code?: string })?.code;
      if (code !== "42P01" && code !== "42501") throw error;
      console.warn(`Catalogue search is not set up (${code})`);
      return c.json({ error: "A busca no catálogo completo ainda não está disponível." }, 503, { "Cache-Control": "no-store" });
    }
  });

  app.post("/api/location", async (c) => {
    const body = await c.req.json().catch(() => null);
    const query = normalize((body as { query?: unknown } | null)?.query);
    if (query.length < MIN_QUERY || query.length > MAX_QUERY) {
      return c.json({ error: `Digite entre ${MIN_QUERY} e ${MAX_QUERY} caracteres do endereço ou bairro.` }, 400);
    }
    try {
      return c.json({ places: await searchAddresses(query, fetchImpl) });
    } catch (error) {
      if (!(error instanceof AddressSearchError)) throw error;
      // The typed text is not logged: it is what the person searched for.
      console.warn("Address search is unavailable");
      return c.json(
        { error: "A busca de endereço está indisponível agora. Tente de novo ou use sua localização." },
        502,
      );
    }
  });

  // The street address for a GPS position, so the UI can show it instead of "my location".
  app.get("/api/location/reverse", async (c) => {
    const latitude = Number(c.req.query("lat"));
    const longitude = Number(c.req.query("lon"));
    const valid =
      c.req.query("lat") && c.req.query("lon") &&
      Number.isFinite(latitude) && Math.abs(latitude) <= 90 &&
      Number.isFinite(longitude) && Math.abs(longitude) <= 180;
    if (!valid) return c.json({ error: "Coordenadas inválidas." }, 400);
    try {
      return c.json({ place: await reverseAddress(latitude, longitude, fetchImpl) });
    } catch (error) {
      if (!(error instanceof AddressSearchError)) throw error;
      // The coordinates are not logged: they are where the person is.
      console.warn("Reverse address lookup is unavailable");
      return c.json({ error: "Não foi possível descobrir o endereço agora." }, 502);
    }
  });

  // Accounts: sign-in (e-mail/password and Google), saved lists and the preferred location.
  app.route("/api", accountRoutes({ store: accountStore, fetchImpl, now }));

  // Placeholder for the *admin* login, which is not the same thing as a shopper's account.
  app.get("/api/session", (c) => c.json({ actor: null }));
  app.delete("/api/session", (c) => c.json({ ok: true }));
  app.post("/api/session", (c) => c.json({ error: "Login depende da integração com o backend." }, 501));

  // Reading a receipt photo runs in Python (scraping/local_api/app.py: OpenCV and a provider key), which a Worker
  // cannot host, so it runs on the VPS behind Caddy (scraping/deploy/Caddyfile.ocr) and this route forwards the
  // upload there. It costs a provider call per photo, so it is rate-limited per address, refused when too big,
  // and sends the shared secret the VPS requires. Not configured (OCR_URL/OCR_SECRET unset): a plain 501.
  app.post("/api/receipt/ocr", async (c) => {
    const { OCR_URL, OCR_SECRET, RECEIPT_LIMITER } = c.env;
    const fail = (message: string, status: 400 | 413 | 429 | 501 | 502, headers: Record<string, string> = {}) =>
      c.json({ error: message }, status, { "Cache-Control": "no-store", ...headers });
    if (!OCR_URL || !OCR_SECRET) return fail("A leitura de cupons ainda não está disponível nesta versão.", 501);

    if (RECEIPT_LIMITER) {
      const { success } = await RECEIPT_LIMITER.limit({ key: c.req.header("CF-Connecting-IP") ?? "unknown" });
      if (!success)
        return fail("Muitas leituras de cupom agora. Tente de novo em instantes.", 429, { "Retry-After": "60" });
    }

    const body = await c.req.arrayBuffer();
    if (body.byteLength === 0) return fail("Envie uma imagem do cupom no campo 'image'.", 400);
    if (body.byteLength > RECEIPT_UPLOAD_MAX_BYTES) return fail("A imagem do cupom é grande demais (máximo 10 MB).", 413);

    let upstream: Response;
    try {
      upstream = await fetchImpl(new URL("/api/receipt/ocr", OCR_URL).toString(), {
        method: "POST",
        headers: { "Content-Type": c.req.header("Content-Type") ?? "", "X-OCR-Secret": OCR_SECRET },
        body,
        signal: AbortSignal.timeout(RECEIPT_TIMEOUT_MS),
      });
    } catch (error) {
      console.error("Receipt OCR host unreachable:", (error as Error)?.message);
      return fail("Não foi possível ler o cupom agora.", 502);
    }
    if (upstream.status === 401) {
      // The VPS does not know our secret: a deploy mistake, nothing the visitor can fix.
      console.error("Receipt OCR host refused the shared secret");
      return fail("O serviço de leitura de cupons está indisponível agora.", 502);
    }
    // The VPS's own answer (the receipt, or its Portuguese error) goes back as it is; only these headers do.
    const headers = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["Content-Type", "Retry-After"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  });

  app.all("/api/*", (c) => c.json({ error: "Não encontrado." }, 404));
  app.onError((error, c) => {
    if ((error as { code?: string })?.code === "42501") {
      console.error("Database permission denied (42501): accounts not configured");
      return c.json({ error: "As contas não estão configuradas neste servidor." }, 503);
    }
    console.error("Request failed", error instanceof Error ? error.message : error);
    return c.json({ error: "Não foi possível carregar as ofertas agora." }, 500);
  });
  return app;
}
