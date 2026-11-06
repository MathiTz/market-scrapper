import { ordinary, type Offer, type Product } from "@/lib/domain";

/** How many results the server may send for one search (the API caps it too). */
export const CATALOGUE_LIMIT = 40;
/** An offer is stale after missing about three scheduled scrapes (SCRAPE_INTERVAL_HOURS * 3 in the publisher). */
const TTL_HOURS = 36;
const CLUB = /(\w*clube\w*)/i;
const GTIN = /^(?:\d{8}|\d{12}|\d{13}|\d{14})$/;

/** One chain's current price, as GET /api/search answers it. */
export type CataloguePrice = {
  store: string;
  price_cents: number;
  regular_price_cents: number | null;
  deal_label: string | null;
  source_url: string | null;
  observed_at: string;
  stock: number | null;
};
export type CatalogueItem = {
  key: string;
  name: string;
  brand: string;
  category: string;
  subcategory: string;
  amount: number;
  unit: "g" | "ml" | "un";
  pack_count: number;
  gtin: string | null;
  image_url: string | null;
  prices: CataloguePrice[];
};
export type CatalogueResponse = { results: CatalogueItem[]; truncated: boolean };

/**
 * GET /api/search: the products of the whole catalogue matching the typed words, which the snapshot does not
 * carry (it holds a capped selection per chain). A failure throws; the caller keeps showing the snapshot's own
 * matches, which are already on screen.
 */
export async function searchCatalogue(query: string, signal: AbortSignal): Promise<CatalogueResponse> {
  const url = `/api/search?q=${encodeURIComponent(query)}&limit=${CATALOGUE_LIMIT}`;
  const response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]) });
  if (!response.ok) throw new Error(`search answered ${response.status}`);
  const body = (await response.json()) as Partial<CatalogueResponse>;
  if (!Array.isArray(body.results)) throw new Error("search answered an unexpected body");
  return { results: body.results, truncated: !!body.truncated };
}

type RetailerRef = { id: string; name: string };

/**
 * The search results as the products and offers the rest of the UI already knows how to show.
 *
 * A result the snapshot already has (an offer of the snapshot has the same `price_key`) is left out, so nothing
 * shows twice; a price of a chain the snapshot does not list as a retailer is left out too, since the UI has
 * nowhere to put it. A product that ends up with no price is not returned.
 */
export function catalogueToData(
  results: CatalogueItem[],
  retailers: RetailerRef[],
  city: string,
  known: ReadonlySet<string>,
  ttlOf: (retailerId: string) => number = () => TTL_HOURS,
): { products: Product[]; offers: Offer[] } {
  const byName = new Map(retailers.map((r) => [r.name, r]));
  const products: Product[] = [];
  const offers: Offer[] = [];
  for (const item of results) {
    if (known.has(item.key)) continue;
    const id = `catalogo-${item.key}`;
    const own = item.prices.flatMap((price) => {
      const retailer = byName.get(price.store);
      return retailer ? offersOf(id, item.key, retailer, city, price, ttlOf(retailer.id)) : [];
    });
    if (!own.length) continue;
    offers.push(...own);
    products.push({
      id,
      name: item.name,
      brand: item.brand,
      category: item.category,
      subcategory: item.subcategory,
      variant: "",
      amount: item.amount,
      unit: item.unit,
      pack_count: item.pack_count,
      gtin: item.gtin && GTIN.test(item.gtin) ? item.gtin : null,
      gtin_evidence: item.gtin && GTIN.test(item.gtin) ? "Código de barras (EAN) informado pela loja." : null,
      ncm: null,
      category_slug: null,
      category_department: null,
      image_url: item.image_url,
      image_source_url: null,
    });
  }
  return { products, offers };
}

function offersOf(
  productId: string,
  key: string,
  retailer: RetailerRef,
  city: string,
  price: CataloguePrice,
  ttlHours: number,
): Offer[] {
  const base = {
    product_id: productId,
    price_key: key,
    retailer_id: retailer.id,
    retailer_name: retailer.name,
    context_id: retailer.id,
    context_label: `${retailer.name} · ${city}`,
    store_phone: null,
    channel: "catalog" as const,
    currency: "BRL",
    stock: price.stock,
    availability: price.stock ? ("available" as const) : ("unknown" as const),
    price_observed_at: price.observed_at,
    source_checked_at: price.observed_at,
    valid_from: null,
    valid_until: null,
    collected_at: price.observed_at,
    source_url: price.source_url ?? "",
    method: "automatic" as const,
    published: 1,
    ttl_hours: ttlHours,
    collection_error: null,
  };
  const id = `${productId}-${retailer.id}`;
  const club = CLUB.exec(price.deal_label ?? "")?.[1];
  if (club && price.regular_price_cents) {
    // A club price is not what everyone pays: the regular price is offered too, without the condition.
    return [
      { ...base, id, price_cents: price.regular_price_cents, regular_price_cents: null, deal_label: null, conditions: ordinary() },
      {
        ...base,
        id: `${id}-club`,
        price_cents: price.price_cents,
        regular_price_cents: price.regular_price_cents,
        deal_label: price.deal_label,
        conditions: { ...ordinary(), club },
      },
    ];
  }
  return [
    {
      ...base,
      id,
      price_cents: price.price_cents,
      regular_price_cents: price.regular_price_cents,
      deal_label: price.deal_label,
      conditions: club ? { ...ordinary(), club } : ordinary(),
    },
  ];
}
