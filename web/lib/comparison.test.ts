import { describe, expect, it } from "vitest";
import { ordinary, type Offer } from "./domain";
import { lowestPriceLabel, outOfComparison, priceSpread, suspiciousSpread } from "./comparison";

const now = new Date("2026-09-27T18:00:00-03:00");
const offer = (cents: number | null, extra: Partial<Offer> = {}) =>
  ({
    id: String(cents),
    price_cents: cents,
    channel: "catalog",
    conditions: ordinary(),
    availability: "unknown",
    price_observed_at: "2026-09-27T15:00:00Z",
    valid_from: null,
    valid_until: null,
    ttl_hours: 36,
    published: 1,
    ...extra,
  }) as Offer;

describe("priceSpread", () => {
  it("is the highest price over the lowest", () => {
    expect(priceSpread([offer(1648), offer(2190)])).toBeCloseTo(1.329, 3);
    expect(priceSpread([offer(500)])).toBe(1);
  });

  it("flags a same-product gap too large to be the same pack (real case: 18 kg box vs one unit)", () => {
    expect(suspiciousSpread([offer(80), offer(4590)])).toBe(true);
    expect(suspiciousSpread([offer(1439), offer(2999)])).toBe(false); // a real promotion, about half price
  });
});

describe("lowestPriceLabel", () => {
  it("does not call a lone price the lowest", () => {
    expect(lowestPriceLabel([offer(999)], 0)).toBe("Único preço atual entre as ofertas monitoradas");
  });

  it("names the lowest, only on the lowest row", () => {
    const ranked = [offer(1648), offer(2190)];
    expect(lowestPriceLabel(ranked, 0)).toBe("Menor preço entre as ofertas monitoradas");
    expect(lowestPriceLabel(ranked, 1)).toBeNull();
  });

  it("calls a tie a tie, on every tied row", () => {
    const ranked = [offer(629), offer(629), offer(709)];
    expect(lowestPriceLabel(ranked, 0)).toBe("Empate no menor preço entre as ofertas monitoradas");
    expect(lowestPriceLabel(ranked, 1)).toBe("Empate no menor preço entre as ofertas monitoradas");
    expect(lowestPriceLabel(ranked, 2)).toBeNull();
  });

  it("narrows the claim to the active filters", () => {
    expect(lowestPriceLabel([offer(1), offer(2)], 0, true)).toBe(
      "Menor preço entre as ofertas monitoradas com os filtros atuais",
    );
  });
});

describe("outOfComparison", () => {
  it("is null for a current offer", () => {
    expect(outOfComparison(offer(100), now)).toBeNull();
  });

  it("tells an outdated price apart from an expired offer", () => {
    const stale = offer(229, { price_observed_at: "2026-09-25T15:00:00Z" });
    expect(outOfComparison(stale, now)).toBe(
      "Preço desatualizado: visto em 25/09 às 12:00 e não confirmado nas últimas 36 h",
    );
    const expired = offer(229, { valid_from: "2026-09-20T00:00:00-03:00", valid_until: "2026-09-22T23:59:59-03:00" });
    expect(outOfComparison(expired, now)).toBe("Validade encerrada em 22/09/2026, 23:59");
  });

  it("explains future, unavailable and unpriced offers", () => {
    expect(outOfComparison(offer(100, { valid_from: "2026-09-30T00:00:00-03:00" }), now)).toMatch(/^Oferta futura/);
    expect(outOfComparison(offer(100, { availability: "unavailable" }), now)).toBe("Indisponível na última consulta à fonte");
    expect(outOfComparison(offer(null), now)).toBe("Sem preço informado pela fonte");
  });
});
