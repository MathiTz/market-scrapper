import { rankOffers, type Offer, type Product } from "./domain";

export function dailyDeals(
  products: Product[],
  offers: Offer[],
  now = new Date(),
) {
  const current = rankOffers(offers, false, now);
  return products
    .flatMap((product) => {
      const prices = current.filter((o) => o.product_id === product.id);
      const best = prices[0];
      const alternative = prices.find(
        (o) => o.retailer_id !== best?.retailer_id,
      );
      if (
        !best?.price_cents ||
        !alternative?.price_cents ||
        alternative.price_cents <= best.price_cents
      )
        return [];
      return [
        {
          product,
          best,
          alternative,
          saving: alternative.price_cents - best.price_cents,
        },
      ];
    })
    .sort(
      (a, b) =>
        b.saving - a.saving ||
        a.product.name.localeCompare(b.product.name, "pt-BR"),
    );
}
