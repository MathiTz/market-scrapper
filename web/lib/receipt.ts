import { clean, rankOffers, type Offer, type Product } from "./domain";
import { listName } from "./format";
import { ABBREVIATIONS, gtinKey, wordSimilarity, wordWeights, type WordWeights } from "./product-match";

/** One line as POST /api/receipt/ocr returns it: reais as printed on the receipt, not cents. */
export type ReceiptItem = {
  line_no: number | null;
  name: string;
  /** The product's barcode when the receipt prints it (checked server-side), else null/absent. */
  code?: string | null;
  qty: number | null;
  unit: string | null;
  unit_price: number | null;
  discount: number | null;
  /** The line's total after its discount. */
  total: number | null;
  printed_total: number | null;
  contested: boolean;
};

export type ReceiptResult = {
  items: ReceiptItem[];
  flags: { bad_math: number[]; missing_lines: number[]; duplicate_lines: number[] };
  failed_tiles: number[];
  /** A slice of the photo could not be read: the items found are real, but some may be missing. */
  degraded: boolean;
};

/**
 * Where what was paid stands against the prices we have for the same product (current, no club/coupon):
 * "inside" the range they span, "below" the lowest (we may be showing an out-of-date price) or "above" the
 * highest, or "no-price" when we have none right now.
 */
export type PriceVerdict = "inside" | "below" | "above" | "no-price";

export type ReceiptComparison = {
  item: ReceiptItem;
  productId: string;
  productName: string;
  /** How the line was recognised: by the barcode it prints (certain) or by its name (likely). */
  via: "code" | "name";
  /** Whether the product is one the shopping list asked for (else it was found in the catalogue). */
  onList: boolean;
  /** What was paid for one unit of what we price (a pack, or a kilo for a weighed item), in cents. */
  paidCents: number | null;
  /** How many of them were bought (packs, or kilos when weighed). */
  quantity: number;
  cheapestCents: number | null;
  cheapestRetailer: string | null;
  highestCents: number | null;
  verdict: PriceVerdict;
};

export type ReceiptReport = {
  comparisons: ReceiptComparison[];
  /** Receipt lines that match nothing on the list - shown, never guessed at. */
  unmatched: ReceiptItem[];
  /** List items no receipt line was matched to. */
  notOnReceipt: { productId: string; name: string }[];
  /** What the matched lines cost above our lowest current price for them, in cents (never negative). */
  overpaidCents: number;
};

/** The shopping-list lines the receipt is checked against. */
export type ListLine = { product_id: string };

/** A price within this many cents of a bound counts as on it: receipts round, and so do we. */
const TOLERANCE_CENTS = 1;
/** A receipt line must be explained this much by a list item (share of its words found in it)... */
const MIN_SCORE = 0.6;
/** ...and beat the next best item by this much, or it is ambiguous and left unmatched. */
const MIN_MARGIN = 0.1;
/** Between equally good names, the price paid must be within this share of the product's price range... */
const PRICE_FITS = 0.1;
/** ...and the next product must be off by this much more, or the price does not tell them apart. */
const PRICE_CLEARLY_BETTER = 0.15;
/** A printed word counts as found at this similarity or above (a prefix or a misread letter; a loose subsequence does too). */
const MIN_WORD_SIMILARITY = 0.6;
/** A line recognised outside the list - from the whole catalogue - has to be explained better: nothing asked for it. */
const MIN_SCORE_OUTSIDE_LIST = 0.75;

const STOPWORDS = new Set(["de", "da", "do", "das", "dos", "e", "com", "sem", "para", "tipo", "un", "und", "unid", "kg", "pct", "cx"]);
const SIZE = /(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b/;
const PACK = /\b(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b/;
/** A size printed with no unit, glued to the word before it: "JUNGLE500" is 500 (g or ml, whichever the product has). */
const BARE_SIZE = /[a-z](\d{3,4})(?!\d)/;

/** `unit` is null for a size printed without one ("JUNGLE500"): the amount is known, the unit is the product's own. */
type Size = { amount: number; unit: "g" | "ml" | null; packs: number };

const toBase = (value: string, unit: string): number => {
  const n = Number(value.replace(",", "."));
  return unit === "kg" || unit === "l" ? n * 1000 : n;
};
const baseUnit = (unit: string): "g" | "ml" => (unit === "kg" || unit === "g" ? "g" : "ml");

/** The size a receipt line states ("1L", "500G", "12X350ML"), or null when it states none. */
export function receiptSize(name: string): Size | null {
  const text = clean(name);
  const pack = PACK.exec(text);
  if (pack) return { amount: toBase(pack[2], pack[3]), unit: baseUnit(pack[3]), packs: Number(pack[1]) };
  const single = SIZE.exec(text);
  if (single) return { amount: toBase(single[1], single[2]), unit: baseUnit(single[2]), packs: 1 };
  const bare = BARE_SIZE.exec(text);
  return bare ? { amount: Number(bare[1]), unit: null, packs: 1 } : null;
}

/**
 * A receipt runs a size and the words around it together ("JUNGLE500TANG" for "Jungle 500ml Tangerina"), which would
 * leave one word that matches nothing. Three digits or more between letters are a size, not part of a word.
 */
const glued = (text: string) => text.replace(/([a-z])(\d{3,})/g, "$1 $2").replace(/(\d{3,})([a-z])/g, "$1 $2");

/** The words of a name that identify the product: no sizes, fillers, or bare numbers. */
export function nameTokens(name: string): string[] {
  const text = glued(clean(name).replace(PACK, " ").replace(SIZE, " "));
  return (text.match(/[a-z0-9]+/g) ?? [])
    .map((word) => ABBREVIATIONS[word] ?? word)
    .filter((word) => word.length >= 2 && !STOPWORDS.has(word) && !/^\d+$/.test(word));
}

/** Whether a receipt line's stated size and unit can be the same thing as this product. */
function sizeAgrees(item: ReceiptItem, product: Product): boolean {
  const weighed = clean(item.unit ?? "") === "kg";
  if (weighed) return product.unit === "g" && product.amount === 1000 && product.pack_count === 1; // priced per kilo
  const size = receiptSize(item.name);
  if (!size) return product.pack_count === 1; // no size to check: only a single pack can be assumed
  if (size.packs !== product.pack_count) return false;
  if (product.unit === "un") return true; // we know no size for it: nothing to contradict
  return (size.unit === null || product.unit === size.unit) && Math.abs(product.amount - size.amount) <= size.amount * 0.01;
}

/** The words of a product that a receipt line can be matched against: its name, brand and variant. */
const productWords = (product: Product) => nameTokens(`${product.name} ${product.brand} ${product.variant}`);

/** How much of a receipt line's words (weighted by how rare they are) the product's name explains, 0 to 1 (0 when its size cannot match). */
function score(item: ReceiptItem, product: Product, weights: WordWeights): number {
  const receiptWords = nameTokens(item.name);
  if (!receiptWords.length || !sizeAgrees(item, product)) return 0;
  const own = productWords(product);
  let explained = 0;
  let total = 0;
  let found = 0;
  for (const word of receiptWords) {
    let best = 0;
    let weight = weights.unmatched;
    for (const candidate of own) {
      const similarity = wordSimilarity(word, candidate);
      if (similarity > best) {
        best = similarity;
        weight = weights.of(candidate);
      }
    }
    explained += weight * best;
    total += weight;
    if (best >= MIN_WORD_SIMILARITY) found++;
  }
  // A single word ("ARROZ") says too little to pick one product, unless the product is as short as that - or
  // the line is weighed: produce prints as one word ("ABACATE"), and the per-kilo gate in sizeAgrees has
  // already narrowed the candidates to products priced by the kilo.
  const weighed = clean(item.unit ?? "") === "kg";
  if (found < 2 && !weighed && !(receiptWords.length === 1 && own.length === 1)) return 0;
  return explained / total;
}

/** What we charge for a product now: the lowest and highest current price, in cents, or null with none. */
type PriceRange = (product: Product) => [number, number] | null;

/** How far a price is outside a range, as a share of the price (0 inside it). */
const distanceFrom = (cents: number, [low, high]: [number, number]) =>
  cents < low ? (low - cents) / cents : cents > high ? (cents - high) / cents : 0;

/**
 * The product a receipt line is, or null when none clearly is. A line cut short ("REF COCA COLA ORIGIN") often
 * fits several sizes of one product equally: those that are the same pack are interchangeable, and otherwise
 * what was paid decides - but only when it fits one of them and clearly not the rest.
 */
function match(
  item: ReceiptItem,
  products: Product[],
  weights: WordWeights,
  rangeOf: PriceRange,
  minScore = MIN_SCORE,
): Product | null {
  const ranked = products
    .map((product) => ({ product, value: score(item, product, weights) }))
    .filter((entry) => entry.value >= minScore)
    .sort((a, b) => b.value - a.value);
  if (!ranked.length) return null;
  const tied = ranked.filter((entry) => ranked[0].value - entry.value < MIN_MARGIN).map((entry) => entry.product);
  if (tied.length === 1) return tied[0];
  const [first] = tied;
  const samePack = (p: Product) =>
    p.unit === first.unit && p.amount === first.amount && p.pack_count === first.pack_count &&
    ((!!p.brand && p.brand === first.brand) || (!!p.gtin && p.gtin === first.gtin));
  if (tied.every(samePack)) return tied.find((p) => rangeOf(p)) ?? first; // the same pack, listed under two names
  const paid = paidPerUnit(item);
  if (paid == null) return null;
  const byPrice = tied
    .map((product) => ({ product, range: rangeOf(product) }))
    .filter((entry): entry is { product: Product; range: [number, number] } => !!entry.range)
    .map((entry) => ({ product: entry.product, off: distanceFrom(paid, entry.range) }))
    .sort((a, b) => a.off - b.off);
  if (!byPrice.length || byPrice[0].off > PRICE_FITS) return null;
  if (byPrice.length > 1 && byPrice[1].off - byPrice[0].off < PRICE_CLEARLY_BETTER) return null;
  return byPrice[0].product;
}

/** What one unit cost after the line's discount, in cents - the weighed price per kilo, or the pack price. */
function paidPerUnit(item: ReceiptItem): number | null {
  const quantity = item.qty && item.qty > 0 ? item.qty : 1;
  const reais = item.total != null ? item.total / quantity : item.unit_price;
  return reais == null ? null : Math.round(reais * 100);
}

/**
 * Checks a read receipt against the shopping list: each line is matched to a list item (only when clearly
 * that one - a wrong match would be a false "you overpaid") and its price compared with our current prices
 * for the product. The receipt does not say which store it came from, so the comparison is against the
 * range across all stores we track, not against one.
 */
export function compareReceipt(
  receipt: ReceiptResult,
  list: ListLine[],
  productById: Map<string, Product>,
  offers: Offer[],
  now = new Date(),
  /** "catalogue": a line that is not on the list is still looked for among everything we price. */
  scope: "list" | "catalogue" = "list",
): ReceiptReport {
  const listed = [...new Set(list.map((line) => line.product_id))]
    .map((id) => productById.get(id))
    .filter((product): product is Product => !!product);
  const offersOf = new Map<string, Offer[]>();
  for (const offer of rankOffers(offers, false, now)) {
    const group = offersOf.get(offer.product_id);
    if (group) group.push(offer);
    else offersOf.set(offer.product_id, [offer]);
  }

  const weights = wordWeights(productById.values(), productWords);
  const listedIds = new Set(listed.map((p) => p.id));
  const byCode = new Map<string, Product[]>();
  const priceable: Product[] = []; // outside the list, only what we have a current price for is worth matching
  for (const product of productById.values()) {
    if (product.gtin) byCode.set(gtinKey(product.gtin), [...(byCode.get(gtinKey(product.gtin)) ?? []), product]);
    if (offersOf.has(product.id) && !listedIds.has(product.id)) priceable.push(product);
  }
  /** The barcode on the line, found among the list's items first and then (if allowed) the catalogue. */
  const matchCode = (item: ReceiptItem): { product: Product; onList: boolean } | null => {
    const sold = item.code ? byCode.get(gtinKey(item.code)) : null;
    if (!sold?.length) return null;
    const onList = sold.find((p) => listedIds.has(p.id));
    if (onList) return { product: onList, onList: true };
    if (scope !== "catalogue") return null;
    const best = [...sold].sort((a, b) => (offersOf.get(b.id)?.length ?? 0) - (offersOf.get(a.id)?.length ?? 0))[0];
    return { product: best, onList: false };
  };

  const rangeOf: PriceRange = (product) => {
    const priced = offersOf.get(product.id); // cheapest first
    return priced?.length ? [priced[0].price_cents!, priced[priced.length - 1].price_cents!] : null;
  };
  const comparisons: ReceiptComparison[] = [];
  const unmatched: ReceiptItem[] = [];
  const seen = new Set<string>();
  for (const item of receipt.items) {
    let found: { product: Product; onList: boolean; via: "code" | "name" } | null = null;
    const coded = matchCode(item);
    if (coded) found = { ...coded, via: "code" };
    else {
      const onList = match(item, listed, weights, rangeOf);
      if (onList) found = { product: onList, onList: true, via: "name" };
      else if (scope === "catalogue") {
        const outside = match(item, priceable, weights, rangeOf, MIN_SCORE_OUTSIDE_LIST);
        if (outside) found = { product: outside, onList: false, via: "name" };
      }
    }
    if (!found) {
      unmatched.push(item);
      continue;
    }
    const { product } = found;
    seen.add(product.id);
    const priced = offersOf.get(product.id) ?? []; // cheapest first, as rankOffers sorts
    const paidCents = paidPerUnit(item);
    const cheapest = priced[0];
    const highest = priced[priced.length - 1];
    let verdict: PriceVerdict = "no-price";
    if (cheapest && highest && paidCents != null) {
      verdict =
        paidCents < cheapest.price_cents! - TOLERANCE_CENTS
          ? "below"
          : paidCents > highest.price_cents! + TOLERANCE_CENTS
            ? "above"
            : "inside";
    }
    comparisons.push({
      item,
      productId: product.id,
      productName: listName(product),
      via: found.via,
      onList: found.onList,
      paidCents,
      quantity: item.qty && item.qty > 0 ? item.qty : 1,
      cheapestCents: cheapest?.price_cents ?? null,
      cheapestRetailer: cheapest?.retailer_name ?? null,
      highestCents: highest?.price_cents ?? null,
      verdict,
    });
  }

  const overpaidCents = comparisons.reduce(
    (sum, c) =>
      c.paidCents != null && c.cheapestCents != null ? sum + Math.max(0, c.paidCents - c.cheapestCents) * c.quantity : sum,
    0,
  );
  return {
    comparisons,
    unmatched,
    notOnReceipt: listed.filter((p) => !seen.has(p.id)).map((p) => ({ productId: p.id, name: listName(p) })),
    overpaidCents: Math.round(overpaidCents),
  };
}
