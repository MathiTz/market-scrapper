import { describe, expect, it } from "vitest";
import { ordinary, type Offer, type Product } from "./domain";
import { dailyDeals } from "./deals";

const now = new Date("2026-09-27T18:00:00-03:00");
const offer = (product: string, retailer: string, cents: number) =>
  ({
    id: `${product}-${retailer}`,
    product_id: product,
    retailer_id: retailer,
    retailer_name: `Rede ${retailer}`,
    channel: "catalog",
    price_cents: cents,
    conditions: ordinary(),
    availability: "unknown",
    price_observed_at: "2026-09-27T15:00:00Z",
    valid_from: null,
    valid_until: null,
    ttl_hours: 36,
    published: 1,
  }) as Offer;
const product = (id: string) => ({ id, name: id }) as unknown as Product;

describe("dailyDeals", () => {
  it("ranks the same product's saving between two chains", () => {
    const deals = dailyDeals([product("lasanha")], [offer("lasanha", "A", 2190), offer("lasanha", "B", 1648)], now);
    expect(deals).toHaveLength(1);
    expect(deals[0].best.retailer_id).toBe("B");
    expect(deals[0].saving).toBe(542);
  });

  it("does not present a gap of 3x or more as a saving (real case: an 18 kg box against one unit)", () => {
    const deals = dailyDeals([product("laranja")], [offer("laranja", "A", 4590), offer("laranja", "B", 80)], now);
    expect(deals).toEqual([]);
  });

  it("needs two different chains", () => {
    expect(dailyDeals([product("x")], [offer("x", "A", 100)], now)).toEqual([]);
  });
});
