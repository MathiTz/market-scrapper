import { clean, type Product } from "@/lib/domain";

// A product's name already carries its size ("Alho Picado Garlic Foods 1kg" / "...400g" / "...2kg" - the
// catalog has no separate, reliable brand field to group by instead, see the note on ProductGroup below).
// Only the size token itself is removed, wherever it falls, not everything after it: several real names
// put the size *before* a flavour or packaging word that must stay ("Lasanha Perdigão 600g Bolonhesa" /
// "...600g Calabresa" - stripping "600g" onward as one earlier version of this did would have thrown away
// "Bolonhesa"/"Calabresa" too and wrongly grouped three different flavours as if they were a size range).
// A name can also carry an earlier, unrelated number ("...15g De Proteina... 250ml": a nutrition claim, not
// the pack size), so every size-shaped token is removed, not just the first or the last.
const SIZE_TOKEN_RE = /\b\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|un(?:idades?)?)\b/gi;

/** `name` with its size token(s) removed - the same product line at any package size. */
export function sizelessName(name: string): string {
  const stripped = name.replace(SIZE_TOKEN_RE, " ").replace(/\s+/g, " ").trim();
  return stripped || name.trim();
}

/** Several sizes of the same product line ("Alho Picado Garlic Foods": 200g, 400g, 1kg, 2kg), shown as one
 * card with a price range instead of one card per size - see components/product-range-card.tsx. */
export type ProductGroup = { key: string; name: string; members: Product[] };

/**
 * `products`, with same-line size variants collapsed into a {@link ProductGroup} - in `products`' own
 * order, at the position of the first variant encountered (so a sort by discount or distance still places
 * the group where its best variant would have landed). A product whose line has no other size present
 * stays a lone product, unchanged.
 *
 * Grouping is by name only, not brand: the catalog's own `brand` field is not populated by the scrapers
 * (every product has `brand: ""`), so "the same name and brand" collapses in practice to "the same name" -
 * the brand text is already part of `name` itself ("... Garlic Foods ..."), so this still tells apart
 * different actual brands, just via the one field that reliably carries that information.
 */
export function groupBySize(products: Product[]): (Product | ProductGroup)[] {
  const keyOf = (p: Product) => clean(sizelessName(p.name));
  const membersByKey = new Map<string, Product[]>();
  for (const p of products) {
    const key = keyOf(p);
    const members = membersByKey.get(key);
    if (members) members.push(p);
    else membersByKey.set(key, [p]);
  }
  const seen = new Set<string>();
  const result: (Product | ProductGroup)[] = [];
  for (const p of products) {
    const key = keyOf(p);
    const members = membersByKey.get(key)!;
    if (members.length < 2) {
      result.push(p);
      continue;
    }
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ key, name: sizelessName(p.name), members });
  }
  return result;
}
