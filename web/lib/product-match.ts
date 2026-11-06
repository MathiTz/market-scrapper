import type { Product } from "./domain";

/**
 * Matching what a receipt prints ("QJO MUSS FAT SADIA 150G") to what we sell ("Queijo Mussarela Fatiado Sadia
 * 150g"): no model, just how receipts abbreviate. A printed word is the start of the real one ("INTEG"), the
 * real one with letters dropped ("BCO"), a known short form ("QJ"), or one misread character away; each is
 * worth less than an exact word. Words that name few products ("mussarela") count for more than ones that
 * name many ("tipo"), so a line is explained by what is rare in it.
 */

/** Short forms a receipt prints that are not the start of the word, as the one word they stand for. */
export const ABBREVIATIONS: Record<string, string> = {
  bco: "branco",
  qj: "queijo",
  qjo: "queijo",
  ref: "refrigerante",
  refri: "refrigerante",
  refrig: "refrigerante",
  beb: "bebida",
  fgo: "frango",
  pres: "presunto",
  mac: "macarrao",
  sh: "shampoo",
  shamp: "shampoo",
  cond: "condicionador",
  ach: "achocolatado",
  achoc: "achocolatado",
  desn: "desnatado",
  integ: "integral",
  gde: "grande",
  pq: "pequeno",
  pcte: "pacote",
  tradic: "tradicional",
};

/** The printed form of a barcode with the zeros some systems pad it with (EAN-13 as GTIN-14) taken off. */
export const gtinKey = (code: string) => code.replace(/\D/g, "").replace(/^0+/, "");

/**
 * The known barcodes (as `gtinKey`s) that `read` is, or is one inserted, dropped or changed digit away from, or has
 * two neighbouring digits swapped from. A model
 * reading a printed barcode usually slips by a digit, which the check digit then rejects; against the barcodes we
 * sell, that slip points at one product. Short reads are left out: with eight digits or fewer, too many barcodes
 * are one slip apart.
 */
export function barcodesNear(read: string, known: ReadonlyMap<string, unknown>): string[] {
  const key = gtinKey(read);
  if (key.length < 11) return [];
  const found = new Set<string>();
  const check = (candidate: string) => known.has(candidate) && found.add(candidate);
  check(key);
  for (let i = 0; i <= key.length; i++) {
    for (let digit = 0; digit <= 9; digit++) check(key.slice(0, i) + digit + key.slice(i)); // a digit dropped from the read
    if (i < key.length) {
      check(key.slice(0, i) + key.slice(i + 1)); // an extra digit in the read
      for (let digit = 0; digit <= 9; digit++) check(key.slice(0, i) + digit + key.slice(i + 1)); // a changed digit
    }
    if (i + 1 < key.length) check(key.slice(0, i) + key[i + 1] + key[i] + key.slice(i + 2)); // two digits swapped
  }
  return [...found].map((candidate) => gtinKey(candidate));
}

const isSubsequence = (small: string, big: string) => {
  let at = 0;
  for (const letter of big) if (letter === small[at]) at++;
  return at === small.length;
};

/** Whether the words differ by one inserted, dropped or changed letter (a misread character). */
function withinOneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  if (i === a.length || i === b.length) return true; // one is the other plus a letter
  if (a.length === b.length) return a.slice(i + 1) === b.slice(i + 1);
  return a.length > b.length ? a.slice(i + 1) === b.slice(i) : a.slice(i) === b.slice(i + 1);
}

/** How well a printed word stands for a product word, from 0 (not at all) to 1 (the same word). */
export function wordSimilarity(printed: string, own: string): number {
  if (printed === own) return 1;
  if (printed.length >= 3 && own.startsWith(printed)) return 0.9;
  if (printed.length >= 5 && printed[0] === own[0] && withinOneEdit(printed, own)) return 0.85;
  // "LNGC" for "linguica": the letters of the printed word appear in order, from the same first letter.
  if (printed.length >= 4 && printed[0] === own[0] && own.length <= printed.length * 2 && isSubsequence(printed, own)) return 0.6;
  return 0;
}

export type WordWeights = {
  /** What a word is worth in explaining a line: more the fewer products carry it. */
  of(word: string): number;
  /** What a printed word that matches nothing costs the line. */
  unmatched: number;
};

/** Word weights from how many of `products` each word appears in (inverse document frequency). */
export function wordWeights(products: Iterable<Product>, tokens: (product: Product) => string[]): WordWeights {
  const counts = new Map<string, number>();
  let total = 0;
  for (const product of products) {
    total++;
    for (const word of new Set(tokens(product))) counts.set(word, (counts.get(word) ?? 0) + 1);
  }
  const weight = (count: number) => Math.log((total + 1) / (count + 1)) + 1;
  return { of: (word) => weight(counts.get(word) ?? 1), unmatched: weight(2) };
}
