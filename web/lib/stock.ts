import type { Offer } from "@/lib/domain";

/**
 * What the store says about its stock, as a plain note, or null when it does not say. It is only
 * information: no threshold and no "only N left" wording.
 */
export function stockNote(offer: Pick<Offer, "stock">): string | null {
  const units = offer.stock;
  if (typeof units !== "number" || !Number.isFinite(units) || units <= 0) return null;
  const count = Math.floor(units);
  return `Estoque informado pela loja: ${new Intl.NumberFormat("pt-BR").format(count)} ${count === 1 ? "unidade" : "unidades"}`;
}
