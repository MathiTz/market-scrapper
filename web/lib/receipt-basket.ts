import { rankOffers, type Offer, type Product } from "./domain";
import { knownSize } from "./format";
import { gtinKey } from "./product-match";
import { nameTokens, type ReceiptComparison } from "./receipt";

/** How the same shopping would have gone at each chain, from the lines of a read receipt. */

/** An equivalent product must carry this share of the bought product's identifying words. */
const MIN_WORD_SHARE = 0.75;
/** ...and cost per kilo/litre within this factor of what was paid, or it is another kind of thing (capsules, pet food). */
const MAX_UNIT_PRICE_FACTOR = 3;

export type LineAtChain = {
  comparison: ReceiptComparison;
  /** "same": the product bought. "similar": another product of the same kind, costed by its price per kg/L. */
  kind: "same" | "similar";
  product: Product;
  offer: Offer;
  /** What one pack of it costs - the amount to actually take to the till. */
  packCents: number;
  /** What the quantity bought would cost there (scaled by weight or volume for a similar product), in cents. */
  costCents: number;
};

export type ChainBasket = {
  retailerId: string;
  retailerName: string;
  lines: LineAtChain[];
  /** Lines of the receipt this chain has no current price (or equivalent) for. */
  missing: ReceiptComparison[];
  totalCents: number;
  /** What was paid for the same lines, so the two can be set side by side. */
  paidCents: number;
};

export type BasketReport = {
  /** Receipt lines with a price paid: what the comparison is about. */
  considered: number;
  paidCents: number;
  /** Chains with at least one line, those that cover every line first, cheapest first. */
  chains: ChainBasket[];
  /** The cheapest chain that has every line. */
  bestSingle: ChainBasket | null;
  /** Each line at its cheapest chain, over the lines at least one chain has. */
  bestSplit: { totalCents: number; paidCents: number; chains: string[]; lines: number } | null;
};

const amountOf = (p: Product) => p.amount * p.pack_count;

/** The words that name what a product is, without its brand or size. */
const coreWords = (p: Product) => {
  const brand = new Set(nameTokens(p.brand));
  return nameTokens(p.name).filter((word) => !brand.has(word));
};

/** Products of the same kind as `anchor` (never `anchor` itself): same tag, same measure, same defining words. */
function equivalents(anchor: Product, byTag: Map<string, Product[]>): Product[] {
  if (!anchor.subcategory || anchor.subcategory === "Outros" || anchor.unit === "un" || !knownSize(anchor)) return [];
  const words = coreWords(anchor);
  if (words.length < 2) return []; // one word ("arroz") names a whole aisle, not a product
  return (byTag.get(anchor.subcategory) ?? []).filter((candidate) => {
    if (candidate.id === anchor.id || candidate.unit !== anchor.unit) return false;
    const own = new Set(coreWords(candidate));
    return words.filter((word) => own.has(word)).length / words.length >= MIN_WORD_SHARE;
  });
}

/**
 * The same receipt lines priced at each chain: the product bought where it is sold, else the cheapest product
 * of the same kind there (same tag and measure, costed by its price per kg or litre for the amount bought).
 * Current ordinary prices only - never a stale one, a club price or a coupon.
 */
export function compareBasket(
  comparisons: ReceiptComparison[],
  productById: Map<string, Product>,
  offers: Offer[],
  now = new Date(),
): BasketReport {
  // The cheapest current offer of each product at each chain.
  const offersOf = new Map<string, Map<string, Offer>>();
  const chains = new Map<string, string>();
  for (const offer of rankOffers(offers, false, now)) {
    chains.set(offer.retailer_id, offer.retailer_name);
    let byChain = offersOf.get(offer.product_id);
    if (!byChain) offersOf.set(offer.product_id, (byChain = new Map()));
    if (!byChain.has(offer.retailer_id)) byChain.set(offer.retailer_id, offer); // rankOffers is cheapest first
  }
  // Chains name one barcode differently, and each name is its own product: they are the same thing on a shelf.
  const sameBarcode = new Map<string, string[]>();
  for (const product of productById.values())
    if (product.gtin && offersOf.has(product.id)) {
      const key = gtinKey(product.gtin);
      sameBarcode.set(key, [...(sameBarcode.get(key) ?? []), product.id]);
    }
  const byTag = new Map<string, Product[]>();
  for (const product of productById.values()) {
    if (!product.subcategory || product.unit === "un" || !knownSize(product) || !offersOf.has(product.id)) continue;
    byTag.set(product.subcategory, [...(byTag.get(product.subcategory) ?? []), product]);
  }

  const used = comparisons.filter((c) => c.paidCents != null && productById.has(c.productId));
  const baskets = new Map<string, ChainBasket>(
    [...chains].map(([retailerId, retailerName]) => [
      retailerId,
      { retailerId, retailerName, lines: [], missing: [], totalCents: 0, paidCents: 0 },
    ]),
  );
  let paidAll = 0;
  for (const comparison of used) {
    const anchor = productById.get(comparison.productId)!;
    const paidLine = comparison.paidCents! * comparison.quantity;
    paidAll += paidLine;
    const bought = comparison.quantity * amountOf(anchor); // in g or ml, when the product has a measure
    const paidPerBase = anchor.unit !== "un" && knownSize(anchor) ? comparison.paidCents! / amountOf(anchor) : null;
    const similar = equivalents(anchor, byTag)
      .map((product) => ({ product, byChain: offersOf.get(product.id)! }))
      .filter(({ product, byChain }) => {
        if (paidPerBase == null) return false;
        const cheapest = Math.min(...[...byChain.values()].map((o) => o.price_cents! / amountOf(product)));
        return cheapest / paidPerBase <= MAX_UNIT_PRICE_FACTOR && cheapest / paidPerBase >= 1 / MAX_UNIT_PRICE_FACTOR;
      });

    for (const basket of baskets.values()) {
      let found: LineAtChain | null = null;
      let same: { product: Product; offer: Offer } | null = null;
      for (const id of anchor.gtin ? (sameBarcode.get(gtinKey(anchor.gtin)) ?? [anchor.id]) : [anchor.id]) {
        const offer = offersOf.get(id)?.get(basket.retailerId);
        if (offer && (!same || offer.price_cents! < same.offer.price_cents!)) same = { product: productById.get(id)!, offer };
      }
      if (same) {
        found = {
          comparison,
          kind: "same",
          product: same.product,
          offer: same.offer,
          packCents: same.offer.price_cents!,
          costCents: Math.round(same.offer.price_cents! * comparison.quantity),
        };
      } else {
        for (const { product, byChain } of similar) {
          const offer = byChain.get(basket.retailerId);
          if (!offer) continue;
          const perBase = offer.price_cents! / amountOf(product);
          if (!found || perBase < found.offer.price_cents! / amountOf(found.product)) {
            found = {
              comparison,
              kind: "similar",
              product,
              offer,
              packCents: offer.price_cents!,
              costCents: Math.round(perBase * bought),
            };
          }
        }
      }
      if (found) {
        basket.lines.push(found);
        basket.totalCents += found.costCents;
        basket.paidCents += paidLine;
      } else basket.missing.push(comparison);
    }
  }

  const withLines = [...baskets.values()].filter((b) => b.lines.length > 0);
  withLines.sort(
    (a, b) =>
      Number(a.missing.length > 0) - Number(b.missing.length > 0) ||
      (a.missing.length > 0 ? a.missing.length - b.missing.length : 0) ||
      a.totalCents - b.totalCents,
  );
  const bestSingle = withLines.find((b) => b.missing.length === 0) ?? null;

  // Each line where it is cheapest.
  let splitTotal = 0;
  let splitPaid = 0;
  let splitLines = 0;
  const splitChains = new Set<string>();
  for (const comparison of used) {
    let best: { cost: number; chain: string } | null = null;
    for (const basket of withLines) {
      const line = basket.lines.find((l) => l.comparison === comparison);
      if (line && (!best || line.costCents < best.cost)) best = { cost: line.costCents, chain: basket.retailerName };
    }
    if (!best) continue;
    splitLines++;
    splitTotal += best.cost;
    splitPaid += comparison.paidCents! * comparison.quantity;
    splitChains.add(best.chain);
  }
  return {
    considered: used.length,
    paidCents: paidAll,
    chains: withLines,
    bestSingle,
    bestSplit: splitLines
      ? { totalCents: splitTotal, paidCents: splitPaid, chains: [...splitChains], lines: splitLines }
      : null,
  };
}
