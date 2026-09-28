import { rankOffers, type Offer, type Product } from "./domain";
import { SUSPECT_SPREAD } from "./comparison";

/**
 * Products whose cheapest current price at one chain beats the next chain's, biggest saving first. A gap of
 * SUSPECT_SPREAD times or more is left out: for the same product it has so far always meant a different unit
 * of sale behind the same name (see lib/comparison.ts), so it is not presented as a saving.
 */
export function dailyDeals(
  products: Product[],
  offers: Offer[],
  now = new Date(),
) {
  // Grouped once (cheapest first, as rankOffers sorts), not filtered again for each of thousands of products.
  const byProduct = new Map<string, Offer[]>();
  for (const o of rankOffers(offers, false, now)) {
    const list = byProduct.get(o.product_id);
    if (list) list.push(o);
    else byProduct.set(o.product_id, [o]);
  }
  return products
    .flatMap((product) => {
      const prices = byProduct.get(product.id) ?? [];
      const best = prices[0];
      const alternative = prices.find(
        (o) => o.retailer_id !== best?.retailer_id,
      );
      if (
        !best?.price_cents ||
        !alternative?.price_cents ||
        alternative.price_cents <= best.price_cents ||
        alternative.price_cents >= best.price_cents * SUSPECT_SPREAD
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
