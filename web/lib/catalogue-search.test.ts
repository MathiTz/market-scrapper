import { afterEach, describe, expect, it, vi } from "vitest";
import { catalogueToData, searchCatalogue, type CatalogueItem } from "./catalogue-search";

const retailers = [
  { id: "1", name: "Atacadão" },
  { id: "2", name: "GBarbosa" },
];
const price = (store: string, cents: number, extra: Partial<CatalogueItem["prices"][number]> = {}) => ({
  store,
  price_cents: cents,
  regular_price_cents: null,
  deal_label: null,
  source_url: `https://${store}/p`,
  observed_at: "2026-11-05T12:00:00+00:00",
  stock: null,
  ...extra,
});
const item = (key: string, prices: CatalogueItem["prices"], extra: Partial<CatalogueItem> = {}): CatalogueItem => ({
  key,
  name: "Arroz Camil Branco 1kg",
  brand: "Camil",
  category: "Mercearia",
  subcategory: "Arroz",
  amount: 1000,
  unit: "g",
  pack_count: 1,
  gtin: null,
  image_url: null,
  prices,
  ...extra,
});

describe("catalogueToData", () => {
  it("turns a result into a product and one offer per chain the snapshot knows", () => {
    const { products, offers } = catalogueToData(
      [item("k1", [price("Atacadão", 549), price("GBarbosa", 499, { regular_price_cents: 599, deal_label: "17% OFF" })])],
      retailers,
      "Fortaleza",
      new Set(),
    );
    expect(products).toHaveLength(1);
    expect(products[0]).toMatchObject({ id: "catalogo-k1", name: "Arroz Camil Branco 1kg", amount: 1000, unit: "g" });
    expect(offers.map((o) => [o.id, o.product_id, o.retailer_id, o.price_cents, o.regular_price_cents, o.deal_label])).toEqual([
      ["catalogo-k1-1", "catalogo-k1", "1", 549, null, null],
      ["catalogo-k1-2", "catalogo-k1", "2", 499, 599, "17% OFF"],
    ]);
    expect(offers[0]).toMatchObject({ price_key: "k1", context_label: "Atacadão · Fortaleza", channel: "catalog", ttl_hours: 36 });
  });

  it("leaves out what the snapshot already shows, by the offers' price key", () => {
    const { products, offers } = catalogueToData([item("k1", [price("Atacadão", 549)])], retailers, "Fortaleza", new Set(["k1"]));
    expect([products, offers]).toEqual([[], []]);
  });

  it("leaves out a chain the snapshot has no retailer for, and a product left with no price", () => {
    const { products, offers } = catalogueToData(
      [item("k1", [price("Outra Rede", 100)]), item("k2", [price("Outra Rede", 100), price("Atacadão", 200)])],
      retailers,
      "Fortaleza",
      new Set(),
    );
    expect(products.map((p) => p.id)).toEqual(["catalogo-k2"]);
    expect(offers.map((o) => o.retailer_id)).toEqual(["1"]);
  });

  it("offers a club price as a conditional one next to the regular price", () => {
    const { offers } = catalogueToData(
      [item("k1", [price("Atacadão", 399, { regular_price_cents: 499, deal_label: "Preço PinClube" })])],
      retailers,
      "Fortaleza",
      new Set(),
    );
    expect(offers).toHaveLength(2);
    expect(offers[0]).toMatchObject({ price_cents: 499, regular_price_cents: null, conditions: { club: null } });
    expect(offers[1]).toMatchObject({ id: "catalogo-k1-1-club", price_cents: 399, conditions: { club: "PinClube" } });
  });

  it("keeps a barcode only when it is a valid one, with its evidence", () => {
    const { products } = catalogueToData(
      [item("k1", [price("Atacadão", 1)], { gtin: "7891234567895" }), item("k2", [price("Atacadão", 1)], { gtin: "123" })],
      retailers,
      "Fortaleza",
      new Set(),
    );
    expect(products[0].gtin).toBe("7891234567895");
    expect(products[0].gtin_evidence).toContain("EAN");
    expect([products[1].gtin, products[1].gtin_evidence]).toEqual([null, null]);
  });

  it("treats a price with stock as available and one without as unknown", () => {
    const { offers } = catalogueToData(
      [item("k1", [price("Atacadão", 1, { stock: 5 }), price("GBarbosa", 1)])],
      retailers,
      "Fortaleza",
      new Set(),
    );
    expect(offers.map((o) => o.availability)).toEqual(["available", "unknown"]);
  });
});

describe("searchCatalogue", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks the API for the typed words, encoded, with the limit", async () => {
    const fetchMock = vi.fn(async (_url: string) => Response.json({ results: [], truncated: false }));
    vi.stubGlobal("fetch", fetchMock);
    await searchCatalogue("feijão preto", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/search?q=feij%C3%A3o%20preto&limit=40");
  });

  it("throws on a failed or malformed answer, so the snapshot's own results stay", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
    await expect(searchCatalogue("arroz", new AbortController().signal)).rejects.toThrow("503");
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ nope: 1 })));
    await expect(searchCatalogue("arroz", new AbortController().signal)).rejects.toThrow("unexpected");
  });
});
