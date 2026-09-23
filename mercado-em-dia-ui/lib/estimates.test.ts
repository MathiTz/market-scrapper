import { describe, expect, it } from "vitest";
import type { Offer } from "./domain";
import { storeEstimates } from "./estimates";
import { groupLocations, type RetailerLocation } from "./location";

const now = new Date().toISOString();
function offer(product: string, store: string, cents: number): Offer {
  return {
    id: `${product}-${store}`,
    product_id: product,
    retailer_id: store,
    retailer_name: `Rede ${store}`,
    context_id: store,
    context_label: `Rede ${store} · Fortaleza`,
    channel: "catalog",
    price_cents: cents,
    currency: "BRL",
    conditions: { club: null, coupon: null, min_quantity: 1, limit_per_customer: null, payment: null, region_note: "" },
    availability: "unknown",
    price_observed_at: now,
    valid_from: null,
    valid_until: null,
    ttl_hours: 48,
    published: 1,
  } as unknown as Offer;
}
// One branch per retailer, at the given coordinates, so a store's "nearest branch" is just its own point.
function locationsOf(...stores: { id: string; lat: number; lon: number }[]) {
  return groupLocations(
    stores.map(
      (s): RetailerLocation => ({
        id: `loc-${s.id}`, retailer_id: s.id, name: s.id, address: `Endereço ${s.id}`,
        latitude: s.lat, longitude: s.lon,
      }),
    ),
  );
}

const lines = [
  { product_id: "arroz", quantity: 2 },
  { product_id: "feijao", quantity: 1 },
  { product_id: "note:abc", quantity: 1 }, // a free-text note: no store can price it
];

describe("storeEstimates", () => {
  const offers = [
    offer("arroz", "A", 1000), offer("feijao", "A", 800),
    offer("arroz", "B", 900), offer("feijao", "B", 700),
    offer("arroz", "C", 500), // C is missing the beans
  ];
  const noLocations = groupLocations([]);

  it("totals each store by price times quantity and lists what each one covers", () => {
    const a = storeEstimates(lines, offers, null, noLocations).find((s) => s.context_id === "A")!;
    expect(a.total).toBe(1000 * 2 + 800);
    expect(a.covered).toBe(2);
    expect(a.items.map((i) => [i.product_id, i.offer?.price_cents ?? null])).toEqual([
      ["arroz", 1000], ["feijao", 800], ["note:abc", null],
    ]);
  });

  it("only ranks a store as cheapest when it covers every item", () => {
    const complete = [{ product_id: "arroz", quantity: 2 }, { product_id: "feijao", quantity: 1 }];
    const result = storeEstimates(complete, offers, null, noLocations);
    expect(result.find((s) => s.cheapest)?.context_id).toBe("B"); // 2*900+700 beats A; C is cheaper but partial
    expect(result.find((s) => s.context_id === "C")?.cheapest).toBe(false);
    expect(result.filter((s) => s.cheapest)).toHaveLength(1);
  });

  it("has no cheapest store when none covers the whole list", () => {
    expect(storeEstimates(lines, offers, null, noLocations).some((s) => s.cheapest)).toBe(false);
  });

  it("marks the closest store once a reference is set", () => {
    const near = [
      offer("arroz", "A", 1000), offer("arroz", "B", 900), offer("arroz", "C", 500),
    ];
    const byRetailer = locationsOf(
      { id: "A", lat: -3.80, lon: -38.50 }, { id: "B", lat: -3.731, lon: -38.50 }, { id: "C", lat: -3.70, lon: -38.50 },
    );
    const nearby = { point: { latitude: -3.73, longitude: -38.5, label: "Rua X", source: "manual" as const }, radiusKm: 5 };
    const result = storeEstimates([{ product_id: "arroz", quantity: 1 }], near, nearby, byRetailer);
    expect(result.find((s) => s.nearest)?.context_id).toBe("B");
    expect(result.find((s) => s.context_id === "B")?.distanceKm).toBeLessThan(0.5);
  });

  it("has no closest store, and no distances, without a reference", () => {
    const result = storeEstimates(lines, offers, null, noLocations);
    expect(result.some((s) => s.nearest)).toBe(false);
    expect(result.every((s) => s.distanceKm === null)).toBe(true);
  });

  it("has no distance for a store whose chain has no known branch, even with a reference", () => {
    const nearby = { point: { latitude: -3.73, longitude: -38.5, label: "Rua X", source: "manual" as const }, radiusKm: 5 };
    const result = storeEstimates(lines, offers, nearby, noLocations);
    expect(result.every((s) => s.distanceKm === null)).toBe(true);
  });

  it("leaves out stores that cover nothing on the list", () => {
    const result = storeEstimates([{ product_id: "arroz", quantity: 1 }], [offer("sal", "Z", 300), ...offers], null, noLocations);
    expect(result.map((s) => s.context_id).sort()).toEqual(["A", "B", "C"]);
  });

  it("carries the store label for the card", () => {
    expect(storeEstimates(lines, offers, null, noLocations)[0].label).toMatch(/Fortaleza/);
  });
});
