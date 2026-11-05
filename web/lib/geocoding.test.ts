import { afterEach, describe, expect, it, vi } from "vitest";
import { addressAt, searchPlaces } from "./geocoding";

function respond(body: unknown, status = 200) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("searchPlaces", () => {
  it("keeps only usable address suggestions", async () => {
    vi.stubGlobal(
      "fetch",
      respond({
        places: [
          { id: "a", label: "Rua A, 10", latitude: -3.72, longitude: -38.5 },
          { id: "b", label: "Sem coordenadas" },
          { id: 3, label: "Rua C", latitude: -3.7, longitude: -38.5 },
          null,
        ],
      }),
    );

    await expect(searchPlaces("Rua A")).resolves.toEqual([
      { id: "a", label: "Rua A, 10", latitude: -3.72, longitude: -38.5 },
    ]);
  });

  it("returns no suggestions when the payload has no list", async () => {
    vi.stubGlobal("fetch", respond({}));
    await expect(searchPlaces("Rua A")).resolves.toEqual([]);
  });

  it("uses the API's message when the search fails", async () => {
    vi.stubGlobal("fetch", respond({ error: "Busca indisponível." }, 503));
    await expect(searchPlaces("Rua A")).rejects.toThrow("Busca indisponível.");
  });

  it("falls back to its own message when the failure has none", async () => {
    vi.stubGlobal("fetch", respond({}, 500));
    await expect(searchPlaces("Rua A")).rejects.toThrow("Não foi possível buscar o endereço agora.");
  });

  it("reports a network failure as a timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(searchPlaces("Rua A")).rejects.toThrow(
      "A busca de endereço demorou mais que o esperado. Tente novamente.",
    );
  });
});

describe("addressAt", () => {
  it("rounds the position and returns the street address", async () => {
    const fetchMock = respond({ place: { label: "Rua A, 10 · Meireles" } });
    vi.stubGlobal("fetch", fetchMock);

    await expect(addressAt(-3.721234, -38.501234)).resolves.toBe("Rua A, 10 · Meireles");
    const url = String((fetchMock as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]);
    expect(url).toContain("lat=-3.7212");
    expect(url).toContain("lon=-38.5012");
  });

  it("returns null when the position has no address", async () => {
    vi.stubGlobal("fetch", respond({}, 404));
    await expect(addressAt(-3.72, -38.5)).resolves.toBeNull();
  });

  it("returns null when the service cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(addressAt(-3.72, -38.5)).resolves.toBeNull();
  });
});
