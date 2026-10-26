import { describe, expect, it } from "vitest";
import { conditionLabel, lastKnownOffers, ordinary, rankOffers, type Offer } from "./domain";

describe("conditionLabel", () => {
  it("says a club price is only for members, without repeating the word", () => {
    expect(conditionLabel({ ...ordinary(), club: "PinClube" })).toBe("Só para membros do PinClube");
    expect(conditionLabel({ ...ordinary(), club: "Clube" })).toBe("Só para membros do clube da loja");
    expect(conditionLabel({ ...ordinary(), club: "Exemplo" })).toBe("Só para membros do Clube Exemplo");
  });

  it("spells out the other conditions, and says when there is none", () => {
    expect(conditionLabel({ ...ordinary(), coupon: "OFERTA10", min_quantity: 3, limit_per_customer: 6 })).toBe(
      "Exige cupom OFERTA10 · Levando 3 un. ou mais · Limite de 6 por cliente",
    );
    expect(conditionLabel(ordinary())).toBe("Sem condição especial");
  });
});

describe("lastKnownOffers", () => {
  const now = new Date("2026-10-26T15:00:00Z");
  const offer = (cents: number | null, extra: Partial<Offer> = {}) =>
    ({
      id: `o${cents}`,
      product_id: "p",
      price_cents: cents,
      channel: "catalog",
      conditions: ordinary(),
      availability: "available",
      price_observed_at: "2026-10-20T12:00:00Z", // six days ago: past a 36 h window
      valid_from: null,
      valid_until: null,
      ttl_hours: 36,
      published: 1,
      ...extra,
    }) as Offer;

  it("returns the prices their store has not confirmed within the window, cheapest first", () => {
    const list = [offer(900), offer(500), offer(700)];
    expect(lastKnownOffers(list, false, now).map((o) => o.price_cents)).toEqual([500, 700, 900]);
  });

  it("never includes a fresh price, which is a current one and ranks as such", () => {
    const fresh = offer(400, { price_observed_at: "2026-10-26T12:00:00Z" });
    expect(lastKnownOffers([fresh, offer(500)], false, now).map((o) => o.price_cents)).toEqual([500]);
    expect(rankOffers([fresh, offer(500)], false, now).map((o) => o.price_cents)).toEqual([400]);
  });

  it("is disjoint from the ranked offers: a price is one or the other, never both", () => {
    const list = [offer(500), offer(400, { price_observed_at: "2026-10-26T12:00:00Z" })];
    const ranked = new Set(rankOffers(list, true, now).map((o) => o.id));
    for (const o of lastKnownOffers(list, true, now)) expect(ranked.has(o.id)).toBe(false);
  });

  it("leaves out what is not merely old: an expired or future promotion, an unavailable item, an unpublished or unpriced one", () => {
    const list = [
      offer(500, { valid_until: "2026-10-22T00:00:00Z" }), // the promotion is over
      offer(510, { valid_from: "2026-11-01T00:00:00Z" }), // not started
      offer(520, { availability: "unavailable" }), // the store said it had none
      offer(530, { published: 0 }),
      offer(null),
      offer(540, { channel: "flyer" }), // a flyer is valid by its dates, never "stale"
    ];
    expect(lastKnownOffers(list, false, now)).toEqual([]);
  });

  it("leaves out a club or coupon price unless conditions are asked for", () => {
    const club = offer(400, { conditions: { ...ordinary(), club: "Clube" } });
    expect(lastKnownOffers([club, offer(500)], false, now).map((o) => o.price_cents)).toEqual([500]);
    expect(lastKnownOffers([club, offer(500)], true, now).map((o) => o.price_cents)).toEqual([400, 500]);
  });
});
