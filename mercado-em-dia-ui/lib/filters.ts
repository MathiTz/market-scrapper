import { rankOffers, type Offer, type Product } from "@/lib/domain";
import { nearestLocation, type Coordinates, type LocationsByRetailer } from "@/lib/location";

export type SortKey = "name" | "price-asc" | "price-desc" | "discount" | "discount-near";

export type ProductFilters = {
  /** Retailer ids to show; empty means every chain. */
  networks: string[];
  /** Minimum discount in percent; 0 means any, 1 means "any discount at all". */
  minDiscount: number;
  /** Price bounds in cents, applied to what a store charges. */
  minPrice: number | null;
  maxPrice: number | null;
  sort: SortKey;
};

export const noFilters: ProductFilters = {
  networks: [],
  minDiscount: 0,
  minPrice: null,
  maxPrice: null,
  sort: "discount-near",
};

/** How many of the filters are set (the sort order is a choice, not a filter). */
export function activeFilterCount(f: ProductFilters): number {
  return (
    (f.networks.length ? 1 : 0) +
    (f.minDiscount > 0 ? 1 : 0) +
    (f.minPrice !== null ? 1 : 0) +
    (f.maxPrice !== null ? 1 : 0)
  );
}

/** The discount an offer gives against its regular price, in whole percent (0 when there is none). */
export function discountPercent(o: Offer): number {
  const regular = o.regular_price_cents;
  if (!regular || o.price_cents === null || o.price_cents >= regular) return 0;
  return Math.round((1 - o.price_cents / regular) * 100);
}

/** "12,50" or "12.5" as cents; null for empty or invalid text. */
export function parseReais(text: string): number | null {
  const value = text.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
  return Math.round(Number(value) * 100);
}

/**
 * The products that pass the filters, in the chosen order. A product passes when at least one current
 * offer meets all of them at once (chain, discount and price range), so "20% off under R$ 10" means
 * a single offer that does both. The cheapest such offer decides the price order; for "discount-near", its
 * chain's nearest real branch to `nearby` decides distance (the same offer the card itself shows as the
 * price, so what is sorted matches what is on screen) - a chain with no known branch there sorts last, not
 * first, since "closest" cannot mean "distance unknown".
 */
export function filterProducts(
  products: Product[],
  offersByProduct: Map<string, Offer[]>,
  f: ProductFilters,
  options: {
    conditions: boolean;
    includeUnpriced: boolean;
    nearby?: Coordinates | null;
    locationsByRetailer?: LocationsByRetailer;
  },
): Product[] {
  const restricted = activeFilterCount(f) > 0;
  const needsDistance = f.sort === "discount-near" && options.nearby && options.locationsByRetailer;
  const rows: { product: Product; price: number | null; discount: number; distanceKm: number | null }[] = [];
  for (const product of products) {
    const offers = rankOffers(offersByProduct.get(product.id) ?? [], options.conditions).filter(
      (o) =>
        (!f.networks.length || f.networks.includes(o.retailer_id)) &&
        (f.minPrice === null || o.price_cents! >= f.minPrice) &&
        (f.maxPrice === null || o.price_cents! <= f.maxPrice) &&
        (f.minDiscount === 0 || discountPercent(o) >= f.minDiscount),
    );
    if (offers.length) {
      const distanceKm = needsDistance
        ? (nearestLocation(options.locationsByRetailer![offers[0].retailer_id], options.nearby!)?.distanceKm ?? null)
        : null;
      rows.push({
        product,
        price: offers[0].price_cents, // rankOffers sorts by price
        discount: Math.max(...offers.map(discountPercent)),
        distanceKm,
      });
    } else if (options.includeUnpriced && !restricted) {
      rows.push({ product, price: null, discount: 0, distanceKm: null });
    }
  }
  const missingLast = (a: number | null, b: number | null, sign: 1 | -1) =>
    a === null ? (b === null ? 0 : 1) : b === null ? -1 : sign * (a - b);
  if (f.sort === "price-asc") rows.sort((a, b) => missingLast(a.price, b.price, 1));
  else if (f.sort === "price-desc") rows.sort((a, b) => missingLast(a.price, b.price, -1));
  else if (f.sort === "discount")
    rows.sort((a, b) => b.discount - a.discount || missingLast(a.price, b.price, 1));
  else if (f.sort === "discount-near")
    rows.sort((a, b) => b.discount - a.discount || missingLast(a.distanceKm, b.distanceKm, 1));
  return rows.map((r) => r.product);
}

/** The products with at least one current, unconditional price: the ones a list can be priced from. */
export function productsWithPrice<T extends { id: string }>(products: T[], offers: Offer[]): T[] {
  const priced = new Set(rankOffers(offers).map((o) => o.product_id));
  return products.filter((p) => priced.has(p.id));
}

/**
 * The product detail page's "Alternativas": other products of the same *kind* as `active` that also have
 * a current price, excluding itself. Prefers subcategory ("Hidratante" next to other Hidratante, not next
 * to every other product loosely filed under "Higiene e beleza" - fralda, absorvente, shampoo...) and
 * only falls back to the coarse category when the ETL found nothing specific enough to name one (see
 * subcategorize() in services/public_api.py) - a product without a subcategory still gets *some*
 * alternatives, just less precise ones, rather than none.
 *
 * `pricedIds` excludes anything with no current offer: a same-kind product nobody is currently selling is
 * not something to compare against, and showing it as an unpriced card ("Sem preço atual") only made the
 * list longer without making it more useful.
 */
export function alternativesOf(products: Product[], active: Product, pricedIds: ReadonlySet<string>): Product[] {
  const sameKind = active.subcategory
    ? (p: Product) => p.subcategory === active.subcategory
    : (p: Product) => p.category === active.category;
  return products.filter((p) => p.id !== active.id && sameKind(p) && pricedIds.has(p.id));
}
