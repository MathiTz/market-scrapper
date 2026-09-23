import { describe, expect, it } from "vitest";
import type { Offer } from "./domain";
import {
  distanceKm,
  filterNearby,
  groupLocations,
  nearestLocation,
  offerLocation,
  type RetailerLocation,
} from "./location";

const FORTALEZA = { latitude: -3.7319, longitude: -38.5267, label: "Centro de Fortaleza", source: "manual" as const };
// A real coordinate near Rua Albatroz, Porto das Dunas, Aquiraz - about 25 km from central Fortaleza.
const AQUIRAZ = { latitude: -3.833, longitude: -38.38, label: "Rua Albatroz, Aquiraz", source: "manual" as const };

const branches: RetailerLocation[] = [
  { id: "l1", retailer_id: "mercadinho", name: "Beira Mar", address: "Av. Beira Mar, Fortaleza", latitude: -3.728, longitude: -38.489 },
  { id: "l2", retailer_id: "mercadinho", name: "Porto das Dunas", address: "Av. Caminho do Sol, Aquiraz", latitude: -3.834, longitude: -38.383 },
  { id: "l3", retailer_id: "atacadao", name: "Fátima", address: "Av. Luciano Carneiro, Fortaleza", latitude: -3.7586, longitude: -38.5347 },
];
const byRetailer = groupLocations(branches);

function offer(retailer_id: string): Offer {
  return {
    id: `${retailer_id}-1`, product_id: "p1", retailer_id, retailer_name: retailer_id,
    context_id: retailer_id, context_label: retailer_id, channel: "catalog", price_cents: 100,
    currency: "BRL",
    conditions: { club: null, coupon: null, min_quantity: 1, limit_per_customer: null, payment: null, region_note: "" },
    availability: "unknown", price_observed_at: "", valid_from: null, valid_until: null, ttl_hours: 48, published: 1,
  } as unknown as Offer;
}

describe("groupLocations", () => {
  it("groups branches by the retailer they belong to", () => {
    expect(byRetailer["mercadinho"]).toHaveLength(2);
    expect(byRetailer["atacadao"]).toHaveLength(1);
    expect(byRetailer["nao-existe"]).toBeUndefined();
  });
});

describe("nearestLocation", () => {
  it("picks the closest of several real branches, not the first one listed", () => {
    const found = nearestLocation(byRetailer["mercadinho"], AQUIRAZ);
    expect(found?.location.name).toBe("Porto das Dunas");
    expect(found!.distanceKm).toBeLessThan(2);
  });

  it("picks the other branch for a reference near central Fortaleza", () => {
    const found = nearestLocation(byRetailer["mercadinho"], FORTALEZA);
    expect(found?.location.name).toBe("Beira Mar");
  });

  it("is null for a retailer with no known branches", () => {
    expect(nearestLocation(byRetailer["cometa"], FORTALEZA)).toBeNull();
    expect(nearestLocation(undefined, FORTALEZA)).toBeNull();
  });
});

describe("offerLocation", () => {
  it("resolves an offer to its chain's nearest branch", () => {
    expect(offerLocation(offer("mercadinho"), byRetailer, AQUIRAZ)?.location.name).toBe("Porto das Dunas");
  });

  it("is null for a chain we have no real branches for", () => {
    expect(offerLocation(offer("sams_club"), byRetailer, AQUIRAZ)).toBeNull();
  });
});

describe("filterNearby", () => {
  const offers = [offer("mercadinho"), offer("atacadao")];

  it("keeps an offer whose chain has a real branch within the radius, by that branch - not a chain-wide point", () => {
    const nearby = { point: AQUIRAZ, radiusKm: 5 } as const;
    const kept = filterNearby(offers, nearby, byRetailer);
    expect(kept.map((o) => o.retailer_id)).toEqual(["mercadinho"]); // Porto das Dunas is close; Fátima is not
  });

  it("returns everything when no reference is set", () => {
    expect(filterNearby(offers, null, byRetailer)).toEqual(offers);
  });

  it("drops an offer from a chain with no known branches", () => {
    const kept = filterNearby([offer("cometa")], { point: FORTALEZA, radiusKm: 20 }, byRetailer);
    expect(kept).toEqual([]);
  });
});

describe("distanceKm sanity for the Aquiraz case", () => {
  it("central Fortaleza to Porto das Dunas is roughly 20-30 km, not walkable", () => {
    const km = distanceKm(FORTALEZA, branches[1]);
    expect(km).toBeGreaterThan(15);
    expect(km).toBeLessThan(35);
  });
});
