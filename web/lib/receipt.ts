import { clean, rankOffers, type Offer, type Product } from "./domain";
import { listName } from "./format";

/** One line as POST /api/receipt/ocr returns it: reais as printed on the receipt, not cents. */
export type ReceiptItem = {
  line_no: number | null;
  name: string;
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

const STOPWORDS = new Set(["de", "da", "do", "das", "dos", "e", "com", "sem", "para", "tipo", "un", "und", "unid", "kg", "pct", "cx"]);
/** Abbreviations a receipt prints that are not a prefix of the word (most are: "INTEG" -> "integral"). */
const ABBREVIATIONS: Record<string, string> = { bco: "branco", qjo: "queijo" };
const SIZE = /(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b/;
const PACK = /\b(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b/;

type Size = { amount: number; unit: "g" | "ml"; packs: number };

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
  return single ? { amount: toBase(single[1], single[2]), unit: baseUnit(single[2]), packs: 1 } : null;
}

/** The words of a name that identify the product: no sizes, fillers, or bare numbers. */
export function nameTokens(name: string): string[] {
  const text = clean(name).replace(PACK, " ").replace(SIZE, " ");
  return (text.match(/[a-z0-9]+/g) ?? [])
    .map((word) => ABBREVIATIONS[word] ?? word)
    .filter((word) => word.length >= 2 && !STOPWORDS.has(word) && !/^\d+$/.test(word));
}

/** A receipt word matches a product word when equal, or when it is the printed start of it ("INTEG"). */
const wordMatches = (receiptWord: string, productWord: string) =>
  receiptWord === productWord || (receiptWord.length >= 3 && productWord.startsWith(receiptWord));

/** Whether a receipt line's stated size and unit can be the same thing as this product. */
function sizeAgrees(item: ReceiptItem, product: Product): boolean {
  const weighed = clean(item.unit ?? "") === "kg";
  if (weighed) return product.unit === "g" && product.amount === 1000 && product.pack_count === 1; // priced per kilo
  const size = receiptSize(item.name);
  if (!size) return product.pack_count === 1; // no size to check: only a single pack can be assumed
  if (size.packs !== product.pack_count) return false;
  if (product.unit === "un") return true; // we know no size for it: nothing to contradict
  return product.unit === size.unit && Math.abs(product.amount - size.amount) <= size.amount * 0.01;
}

/** The share of a receipt line's words found in the product's name (0 when its size cannot match). */
function score(item: ReceiptItem, product: Product): number {
  const receiptWords = nameTokens(item.name);
  if (!receiptWords.length || !sizeAgrees(item, product)) return 0;
  const productWords = nameTokens(`${product.name} ${product.brand} ${product.variant}`);
  const found = receiptWords.filter((word) => productWords.some((own) => wordMatches(word, own))).length;
  // A single word ("ARROZ") says too little to pick one product, unless the product is as short as that - or
  // the line is weighed: produce prints as one word ("ABACATE"), and the per-kilo gate in sizeAgrees has
  // already narrowed the candidates to products priced by the kilo.
  const weighed = clean(item.unit ?? "") === "kg";
  if (found < 2 && !weighed && !(receiptWords.length === 1 && productWords.length === 1)) return 0;
  return found / receiptWords.length;
}

/** The list item a receipt line is, or null when none clearly is (low score, or two nearly tied). */
function match(item: ReceiptItem, products: Product[]): Product | null {
  const ranked = products
    .map((product) => ({ product, value: score(item, product) }))
    .filter((entry) => entry.value >= MIN_SCORE)
    .sort((a, b) => b.value - a.value);
  if (!ranked.length) return null;
  if (ranked.length > 1 && ranked[0].value - ranked[1].value < MIN_MARGIN) return null;
  return ranked[0].product;
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

  const comparisons: ReceiptComparison[] = [];
  const unmatched: ReceiptItem[] = [];
  const seen = new Set<string>();
  for (const item of receipt.items) {
    const product = match(item, listed);
    if (!product) {
      unmatched.push(item);
      continue;
    }
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
