import { describe, expect, it } from "vitest";
import type { Offer, Product } from "./domain";
import { activeFilterCount, alternativesOf, discountPercent, filterProducts, noFilters, parseReais, productsWithPrice } from "./filters";
import { groupLocations, type RetailerLocation } from "./location";

const now = new Date().toISOString();
function offer(product: string, store: string, cents: number, regular: number | null = null, club: string | null = null): Offer {
  return {
    id: `${product}-${store}`, product_id: product, retailer_id: store, retailer_name: `Rede ${store}`,
    context_id: store, context_label: `Rede ${store}`, channel: "catalog", price_cents: cents,
    regular_price_cents: regular, currency: "BRL",
    conditions: { club, coupon: null, min_quantity: 1, limit_per_customer: null, payment: null, region_note: "" },
    availability: "unknown", price_observed_at: now, valid_from: null, valid_until: null, ttl_hours: 48, published: 1,
  } as unknown as Offer;
}
const product = (id: string, name = id) => ({ id, name }) as unknown as Product;

const products = ["arroz", "feijao", "cafe", "sal"].map((id) => product(id));
const byProduct = (offers: Offer[]) => {
  const map = new Map<string, Offer[]>();
  for (const o of offers) map.set(o.product_id, [...(map.get(o.product_id) ?? []), o]);
  return map;
};
const offers = [
  offer("arroz", "A", 2000, 2500), // 20% off
  offer("arroz", "B", 2200),
  offer("feijao", "A", 800, 1000), // 20% off
  offer("cafe", "B", 1500, 3000), // 50% off
  // "sal" has no offers at all
];
const names = (list: Product[]) => list.map((p) => p.id);
const run = (f = {}, o = {}) =>
  names(filterProducts(products, byProduct(offers), { ...noFilters, ...f }, { conditions: false, includeUnpriced: false, ...o }));

describe("discountPercent", () => {
  it("is the share taken off the regular price, and 0 without one", () => {
    expect(discountPercent(offer("x", "A", 750, 1000))).toBe(25);
    expect(discountPercent(offer("x", "A", 1000))).toBe(0);
    expect(discountPercent(offer("x", "A", 1200, 1000))).toBe(0);
  });
});

describe("parseReais", () => {
  it("reads Brazilian and plain decimals as cents", () => {
    expect(parseReais("12,50")).toBe(1250);
    expect(parseReais("12.5")).toBe(1250);
    expect(parseReais(" 7 ")).toBe(700);
  });
  it("is null for empty or invalid text", () => {
    for (const bad of ["", "abc", "-3", "1,234", "1,2,3"]) expect(parseReais(bad)).toBeNull();
  });
});

describe("filterProducts", () => {
  it("shows every product with a current price when nothing is set", () => {
    expect(run().sort()).toEqual(["arroz", "cafe", "feijao"]);
  });

  it("filters by several chains at once", () => {
    expect(run({ networks: ["A"] }).sort()).toEqual(["arroz", "feijao"]);
    expect(run({ networks: ["A", "B"] }).sort()).toEqual(["arroz", "cafe", "feijao"]);
    expect(run({ networks: ["Z"] })).toEqual([]);
  });

  it("filters by discount", () => {
    expect(run({ minDiscount: 1 }).sort()).toEqual(["arroz", "cafe", "feijao"]);
    expect(run({ minDiscount: 30 })).toEqual(["cafe"]);
    expect(run({ minDiscount: 60 })).toEqual([]);
  });

  it("filters by price range, inclusive", () => {
    expect(run({ maxPrice: 1500 }).sort()).toEqual(["cafe", "feijao"]);
    expect(run({ minPrice: 1500, maxPrice: 2000 }).sort()).toEqual(["arroz", "cafe"]);
  });

  it("needs one offer to meet every filter at once", () => {
    // arroz is 20% off only at A (R$ 20,00) and is cheap only at... B costs more: no single offer is both
    expect(run({ minDiscount: 20, maxPrice: 1900 }).sort()).toEqual(["cafe", "feijao"]);
    expect(run({ networks: ["B"], minDiscount: 1 })).toEqual(["cafe"]);
  });

  it("sorts by the cheapest matching offer, with unpriced products last", () => {
    expect(run({ sort: "price-asc" })).toEqual(["feijao", "cafe", "arroz"]);
    expect(run({ sort: "price-desc" })).toEqual(["arroz", "cafe", "feijao"]);
    const withUnpriced = names(filterProducts(products, byProduct(offers), { ...noFilters, sort: "price-asc" }, { conditions: false, includeUnpriced: true }));
    expect(withUnpriced).toEqual(["feijao", "cafe", "arroz", "sal"]);
  });

  it("sorts by the biggest discount", () => {
    expect(run({ sort: "discount" })).toEqual(["cafe", "feijao", "arroz"]);
  });

  describe("discount-near", () => {
    // Both tied at 20% off, so a plain "discount" sort cannot tell them apart; "perto" is at A's real
    // branch (close), "longe" only at B's (far), each at its own chain's best price.
    const perto = product("perto"), longe = product("longe");
    const tied = [offer("perto", "A", 800, 1000), offer("longe", "B", 800, 1000)];
    const tiedByProduct = byProduct(tied);
    const here = { latitude: 0, longitude: 0 };
    const locationsByRetailer = groupLocations([
      { id: "a", retailer_id: "A", name: "A", address: "", latitude: 0.01, longitude: 0 },
      { id: "b", retailer_id: "B", name: "B", address: "", latitude: 10, longitude: 0 },
    ] as RetailerLocation[]);
    const sorted = (opts: Partial<Parameters<typeof filterProducts>[3]>) =>
      names(filterProducts([perto, longe], tiedByProduct, { ...noFilters, sort: "discount-near" },
        { conditions: false, includeUnpriced: false, ...opts }));

    it("without a reference point, a discount tie keeps the products' own order", () => {
      expect(sorted({})).toEqual(["perto", "longe"]);
    });

    it("with a reference, a discount tie is broken by the nearest branch of the cheapest offer's chain", () => {
      expect(sorted({ nearby: here, locationsByRetailer })).toEqual(["perto", "longe"]);
      // Flip which chain is close, and the order flips with it - it is the distance doing the sorting.
      const flipped = groupLocations([
        { id: "a", retailer_id: "A", name: "A", address: "", latitude: 10, longitude: 0 },
        { id: "b", retailer_id: "B", name: "B", address: "", latitude: 0.01, longitude: 0 },
      ] as RetailerLocation[]);
      expect(sorted({ nearby: here, locationsByRetailer: flipped })).toEqual(["longe", "perto"]);
    });

    it("a chain with no known branch sorts after one with a known distance, not before it", () => {
      const onlyA = groupLocations([
        { id: "a", retailer_id: "A", name: "A", address: "", latitude: 0.01, longitude: 0 },
      ] as RetailerLocation[]); // B (longe's chain) has no known branch at all
      expect(sorted({ nearby: here, locationsByRetailer: onlyA })).toEqual(["perto", "longe"]);
    });

    it("discount still comes first: a bigger discount beats a closer branch", () => {
      const mixed = byProduct([offer("perto", "A", 900, 1000), offer("longe", "B", 500, 1000)]); // 10% vs 50%
      const result = names(filterProducts([perto, longe], mixed, { ...noFilters, sort: "discount-near" },
        { conditions: false, includeUnpriced: false, nearby: here, locationsByRetailer }));
      expect(result).toEqual(["longe", "perto"]); // longe's 50% off wins even though it is the far chain
    });
  });

  it("keeps products without a price only when asked and no filter is set", () => {
    const included = (f = {}) => names(filterProducts(products, byProduct(offers), { ...noFilters, ...f }, { conditions: false, includeUnpriced: true }));
    expect(included()).toContain("sal");
    expect(included({ minDiscount: 1 })).not.toContain("sal");
    expect(included({ networks: ["A"] })).not.toContain("sal");
  });

  it("leaves out club prices unless conditions are included", () => {
    const withClub = [...offers, offer("sal", "A", 300, 400, "Clube")];
    const list = (conditions: boolean) => names(filterProducts(products, byProduct(withClub), noFilters, { conditions, includeUnpriced: false }));
    expect(list(false)).not.toContain("sal");
    expect(list(true)).toContain("sal");
  });
});

describe("activeFilterCount", () => {
  it("counts the filters that are set, not the sort order", () => {
    expect(activeFilterCount(noFilters)).toBe(0);
    expect(activeFilterCount({ ...noFilters, sort: "price-asc" })).toBe(0);
    expect(activeFilterCount({ ...noFilters, networks: ["A"], minDiscount: 10, maxPrice: 500 })).toBe(3);
  });
});

describe("productsWithPrice", () => {
  it("keeps only products that have a current, unconditional price", () => {
    const stale = { ...offer("cafe", "A", 900), price_observed_at: new Date(Date.now() - 400 * 3600000).toISOString() } as Offer;
    const club = offer("sal", "A", 300, 400, "Clube");
    const list = productsWithPrice(products, [offer("arroz", "A", 1000), stale, club]);
    expect(names(list)).toEqual(["arroz"]); // cafe's only price is stale, sal's needs a club, feijao has none
  });
});

describe("alternativesOf", () => {
  const withKind = (id: string, category: string, subcategory: string) =>
    ({ id, name: id, category, subcategory }) as unknown as Product;
  const allPriced = new Set(["hidratante-ype", "hidratante-nivea", "absorvente", "cadeira-praia", "guarda-sol"]);

  it("matches by subcategory when the active product has one, ignoring the coarser category match", () => {
    const hidratante = withKind("hidratante-ype", "Higiene e beleza", "Hidratante");
    const list = [
      hidratante,
      withKind("hidratante-nivea", "Higiene e beleza", "Hidratante"), // same subcategory: an alternative
      withKind("absorvente", "Higiene e beleza", "Absorvente"), // same category, different kind: not one
    ];
    expect(alternativesOf(list, hidratante, allPriced).map((p) => p.id)).toEqual(["hidratante-nivea"]);
  });

  it("falls back to category when the active product has no subcategory", () => {
    const noKind = withKind("cadeira-praia", "Outros", "");
    const list = [
      noKind,
      withKind("guarda-sol", "Outros", ""), // same category: still an alternative, since neither has a kind
      withKind("hidratante-ype", "Higiene e beleza", "Hidratante"), // different category: not one
    ];
    expect(alternativesOf(list, noKind, allPriced).map((p) => p.id)).toEqual(["guarda-sol"]);
  });

  it("never includes the active product itself", () => {
    const hidratante = withKind("hidratante-ype", "Higiene e beleza", "Hidratante");
    expect(alternativesOf([hidratante], hidratante, allPriced)).toEqual([]);
  });

  it("excludes a same-kind product with no current price", () => {
    const hidratante = withKind("hidratante-ype", "Higiene e beleza", "Hidratante");
    const unpriced = withKind("hidratante-nivea", "Higiene e beleza", "Hidratante");
    const list = [hidratante, unpriced];
    expect(alternativesOf(list, hidratante, new Set(["hidratante-ype"]))).toEqual([]);
  });
});
