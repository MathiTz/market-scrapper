import { conditionLabel, type Offer } from "./domain";

export function productCardConditions(offer: Offer) {
  const conditions = { ...offer.conditions };
  if (
    offer.channel === "catalog" &&
    conditions.region_note.trim() === "Preço online; valor na loja pode variar."
  )
    conditions.region_note = "";
  return conditionLabel(conditions);
}
