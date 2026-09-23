import { describe, expect, it, vi } from "vitest";
import { createApp } from "./app";
import type { Snapshot, SnapshotStore } from "./store";

const env = { HYPERDRIVE: { connectionString: "postgres://unused" } };

const snapshot = (etag: string): Snapshot => ({
  etag,
  generatedAt: "2026-09-21T15:00:00.000Z",
  payload: `{"products":[{"name":"Café"}],"etag":"${etag}"}`,
});

function fakeStore(initial: Snapshot | null) {
  let current = initial;
  const store: SnapshotStore = {
    latestMeta: vi.fn(async () => (current ? { etag: current.etag, generatedAt: current.generatedAt } : null)),
    latest: vi.fn(async () => current),
  };
  return { store, publish: (next: Snapshot | null) => (current = next) };
}

const appWith = (initial: Snapshot | null, fetchImpl?: typeof fetch) => {
  const db = fakeStore(initial);
  return { ...db, app: createApp({ store: () => db.store, fetchImpl }) };
};

describe("GET /api/public", () => {
  it("sends the latest payload untouched, with caching headers", async () => {
    const { app } = appWith(snapshot("v1"));
    const res = await app.request("/api/public", {}, env);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("application/json");
    expect(res.headers.get("ETag")).toBe('"v1"');
    expect(res.headers.get("Cache-Control")).toContain("max-age=60");
    expect(await res.text()).toBe(snapshot("v1").payload); // byte for byte, accents included
  });

  it("answers 304 when the browser already has the current version", async () => {
    const { app, store } = appWith(snapshot("v1"));
    const res = await app.request("/api/public", { headers: { "If-None-Match": '"v1"' } }, env);
    expect(res.status).toBe(304);
    expect(await res.text()).toBe("");
    expect(store.latest).not.toHaveBeenCalled(); // the payload was never read
  });

  it("does not read the payload again while the etag is unchanged", async () => {
    const { app, store } = appWith(snapshot("v1"));
    await app.request("/api/public", {}, env);
    await app.request("/api/public", {}, env);
    expect(store.latest).toHaveBeenCalledTimes(1);
  });

  it("serves the new payload as soon as a new snapshot is published", async () => {
    const { app, publish } = appWith(snapshot("v1"));
    await app.request("/api/public", {}, env);
    publish(snapshot("v2"));
    const res = await app.request("/api/public", { headers: { "If-None-Match": '"v1"' } }, env);
    expect(res.status).toBe(200);
    expect(res.headers.get("ETag")).toBe('"v2"');
    expect(await res.text()).toContain('"etag":"v2"');
  });

  it("says the data is not published yet, and does not let that be cached", async () => {
    const { app } = appWith(null);
    const res = await app.request("/api/public", {}, env);
    expect(res.status).toBe(503);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect((await res.json()) as { error: string }).toHaveProperty("error");
  });

  it("reports a database failure as a JSON 500 without leaking details", async () => {
    const store: SnapshotStore = {
      latestMeta: async () => {
        throw new Error("password authentication failed for user secret");
      },
      latest: async () => null,
    };
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await createApp({ store: () => store }).request("/api/public", {}, env);
    spy.mockRestore();
    expect(res.status).toBe(500);
    expect(JSON.stringify(await res.json())).not.toContain("secret");
  });
});

const photon = {
  features: [
    {
      geometry: { type: "Point", coordinates: [-38.5021, -3.7247] },
      properties: { osm_type: "W", osm_id: 1, name: "Atlantis Beira-Mar", street: "Avenida Beira Mar", housenumber: "2120", district: "Meireles", city: "Fortaleza" },
    },
    { geometry: { type: "Point", coordinates: [-38.5104, -3.7206] }, properties: { osm_type: "W", osm_id: 2, name: "Avenida Beira Mar", district: "Meireles", city: "Fortaleza" } },
    { geometry: { type: "Point", coordinates: [-38.5047, -3.7232] }, properties: { osm_type: "W", osm_id: 3, name: "Avenida Beira Mar", district: "Meireles", city: "Fortaleza" } },
    { geometry: { type: "LineString", coordinates: [[0, 0]] }, properties: { osm_id: 4, name: "Rota" } },
    { geometry: { type: "Point", coordinates: [-38.5, -3.7] }, properties: { name: "Sem id" } },
  ],
};

const search = (app: ReturnType<typeof createApp>, body: unknown) =>
  app.request("/api/location", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, env);

describe("POST /api/location", () => {
  it("returns places with a label and coordinates", async () => {
    const fetchImpl = vi.fn(async () => Response.json(photon)) as unknown as typeof fetch;
    const { app } = appWith(null, fetchImpl);
    const res = await search(app, { query: "  Av. Beira   Mar " });
    const { places } = (await res.json()) as { places: { id: string; label: string; latitude: number; longitude: number }[] };
    expect(places[0]).toEqual({
      id: "W1",
      label: "Atlantis Beira-Mar · Avenida Beira Mar, 2120 · Meireles · Fortaleza",
      latitude: -3.7247,
      longitude: -38.5021,
    });
    expect(places.map((p) => p.id)).toEqual(["W1", "W2"]); // duplicate label, non-point and id-less results dropped
  });

  it("limits the search to Fortaleza and identifies itself", async () => {
    const fetchImpl = vi.fn(async () => Response.json(photon));
    await search(appWith(null, fetchImpl as unknown as typeof fetch).app, { query: "beira mar" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const params = new URL(url).searchParams;
    expect(params.get("q")).toBe("beira mar");
    expect(params.get("bbox")).toBe("-38.65,-3.95,-38.35,-3.65");
    expect((init.headers as Record<string, string>)["User-Agent"]).toContain("mercado-em-dia");
  });

  it.each([{ query: "ab" }, { query: "x".repeat(121) }, {}, { query: null }, { query: 42 }])(
    "rejects an invalid query without calling the service: %j",
    async (body) => {
      const fetchImpl = vi.fn();
      const res = await search(appWith(null, fetchImpl as unknown as typeof fetch).app, body);
      expect(res.status).toBe(400);
      expect(fetchImpl).not.toHaveBeenCalled();
    },
  );

  it("rejects a body that is not JSON", async () => {
    const { app } = appWith(null, vi.fn() as unknown as typeof fetch);
    const res = await app.request("/api/location", { method: "POST", body: "not json" }, env);
    expect(res.status).toBe(400);
  });

  it.each([
    ["the service is down", async () => new Response("no", { status: 503 })],
    ["the network fails", async () => Promise.reject(new TypeError("fetch failed"))],
  ])("answers 502 when %s", async (_name, impl) => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const res = await search(appWith(null, impl as unknown as typeof fetch).app, { query: "beira mar" });
    spy.mockRestore();
    expect(res.status).toBe(502);
    expect(((await res.json()) as { error: string }).error).toContain("indisponível");
  });
});

describe("GET /api/location/reverse", () => {
  const reverse = (app: ReturnType<typeof createApp>, query: string) => app.request(`/api/location/reverse?${query}`, {}, env);
  const found = {
    features: [{
      geometry: { type: "Point", coordinates: [-38.5021, -3.7247] },
      properties: { osm_type: "W", osm_id: 9, name: "Atlantis Beira-Mar", street: "Avenida Beira Mar", housenumber: "2120", district: "Meireles", city: "Fortaleza" },
    }],
  };

  it("returns the address at the position", async () => {
    const fetchImpl = vi.fn(async () => Response.json(found));
    const res = await reverse(appWith(null, fetchImpl as unknown as typeof fetch).app, "lat=-3.72468&lon=-38.50215");
    expect(res.status).toBe(200);
    expect(((await res.json()) as { place: { label: string } }).place.label).toBe(
      "Atlantis Beira-Mar · Avenida Beira Mar, 2120 · Meireles · Fortaleza",
    );
  });

  it("rounds the position before sending it on (about 11 m)", async () => {
    const fetchImpl = vi.fn(async () => Response.json(found));
    await reverse(appWith(null, fetchImpl as unknown as typeof fetch).app, "lat=-3.724689123&lon=-38.502151999");
    const url = new URL((fetchImpl.mock.calls[0] as unknown as [string])[0]);
    expect(url.pathname).toBe("/reverse");
    expect([url.searchParams.get("lat"), url.searchParams.get("lon")]).toEqual(["-3.7247", "-38.5022"]);
  });

  it("answers place: null when nothing is there", async () => {
    const fetchImpl = vi.fn(async () => Response.json({ features: [] }));
    const res = await reverse(appWith(null, fetchImpl as unknown as typeof fetch).app, "lat=0&lon=0");
    expect(await res.json()).toEqual({ place: null });
  });

  it.each(["", "lat=abc&lon=1", "lat=91&lon=0", "lat=0&lon=181", "lat=-3.7"])("rejects invalid coordinates (%s) without calling the service", async (query) => {
    const fetchImpl = vi.fn();
    const res = await reverse(appWith(null, fetchImpl as unknown as typeof fetch).app, query);
    expect(res.status).toBe(400);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("answers 502 when the service fails", async () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const res = await reverse(appWith(null, (async () => new Response("no", { status: 500 })) as unknown as typeof fetch).app, "lat=-3.7&lon=-38.5");
    spy.mockRestore();
    expect(res.status).toBe(502);
  });
});

describe("other routes", () => {
  it("keeps the session placeholder answers of the old backend", async () => {
    const { app } = appWith(null);
    expect(await (await app.request("/api/session", {}, env)).json()).toEqual({ actor: null });
    expect(await (await app.request("/api/session", { method: "DELETE" }, env)).json()).toEqual({ ok: true });
    expect((await app.request("/api/session", { method: "POST" }, env)).status).toBe(501);
  });

  it("has a health check and a JSON 404 for unknown API paths", async () => {
    const { app } = appWith(null);
    expect(await (await app.request("/api/health", {}, env)).json()).toEqual({ ok: true });
    const missing = await app.request("/api/nope", {}, env);
    expect(missing.status).toBe(404);
    expect(missing.headers.get("Content-Type")).toContain("application/json");
  });
});
