import { Hono } from "hono";
import {
  AddressSearchError,
  MAX_QUERY,
  MIN_QUERY,
  normalize,
  reverseAddress,
  searchAddresses,
} from "./geocoding";
import type { Snapshot, SnapshotStore } from "./store";

export type Bindings = { HYPERDRIVE: { connectionString: string } };

type Deps = {
  store: (env: Bindings) => SnapshotStore;
  fetchImpl?: typeof fetch;
};

// Data changes when a scrape is published (hours apart): browsers reuse it for a minute and may show
// a stale copy for five more while they refresh it; revalidating with the etag costs almost nothing.
const CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300";

export function createApp({ store, fetchImpl = fetch }: Deps) {
  const app = new Hono<{ Bindings: Bindings }>();
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

  // Placeholder for the admin login: the UI expects these answers until real accounts exist.
  app.get("/api/session", (c) => c.json({ actor: null }));
  app.delete("/api/session", (c) => c.json({ ok: true }));
  app.post("/api/session", (c) => c.json({ error: "Login depende da integração com o backend." }, 501));

  app.all("/api/*", (c) => c.json({ error: "Não encontrado." }, 404));
  app.onError((error, c) => {
    console.error("Request failed", error instanceof Error ? error.message : error);
    return c.json({ error: "Não foi possível carregar as ofertas agora." }, 500);
  });
  return app;
}
