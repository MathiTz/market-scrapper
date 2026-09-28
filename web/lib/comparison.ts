import { localTime, offerState, type Offer } from "./domain";
import { whenLabel } from "./format";

/**
 * Prices of one product that differ by this factor or more are shown with a warning and no savings claim.
 * In the published snapshot of 27/09/2026 every such case (4 of 92 products sold by two or more chains) was
 * a name sold by a different unit at each chain - a whole 18 kg box against a price per unit, a price per
 * 100 g against a price per kg - not a real price gap. The match itself is decided by the data pipeline
 * (match_products in services/public_api.py); this only keeps the UI from presenting it as a sure saving.
 */
export const SUSPECT_SPREAD = 3;

/** The highest price divided by the lowest, among priced offers; 1 with fewer than two. */
export function priceSpread(offers: Pick<Offer, "price_cents">[]): number {
  const prices = offers.map((o) => o.price_cents).filter((p): p is number => typeof p === "number" && p > 0);
  if (prices.length < 2) return 1;
  return Math.max(...prices) / Math.min(...prices);
}

export const suspiciousSpread = (offers: Pick<Offer, "price_cents">[]) => priceSpread(offers) >= SUSPECT_SPREAD;

/**
 * The note on a comparison row with the lowest price, or null for the others. Limited to what was actually
 * compared: a single price is not "the lowest", a tie is a tie, and active filters narrow the claim.
 */
export function lowestPriceLabel(
  ranked: Pick<Offer, "price_cents">[],
  index: number,
  filtered = false,
): string | null {
  const row = ranked[index];
  if (!row || row.price_cents === null || row.price_cents !== ranked[0].price_cents) return null;
  const scope = filtered ? " com os filtros atuais" : "";
  if (ranked.length === 1) return `Único preço atual entre as ofertas monitoradas${scope}`;
  const tied = ranked.filter((o) => o.price_cents === row.price_cents).length;
  return tied > 1
    ? `Empate no menor preço entre as ofertas monitoradas${scope}`
    : `Menor preço entre as ofertas monitoradas${scope}`;
}

/**
 * Why a published offer of a product is left out of its comparison, in words, or null when it is current.
 * An expired offer (its validity ended) and an outdated one (not seen again recently) are different things.
 */
export function outOfComparison(o: Offer, now = new Date()): string | null {
  if (o.price_cents === null) return "Sem preço informado pela fonte";
  const state = offerState(o, now);
  if (state === "future") return `Oferta futura: válida a partir de ${localTime(o.valid_from!)}`;
  if (state === "expired") return `Validade encerrada em ${localTime(o.valid_until!)}`;
  if (state === "stale")
    return `Preço desatualizado: visto ${whenLabel(o.price_observed_at, now)} e não confirmado nas últimas ${o.ttl_hours} h`;
  if (state === "unavailable") return "Indisponível na última consulta à fonte";
  return null;
}
