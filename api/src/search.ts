/** The full-catalogue search's rules, the same as scraping/services/catalogue_search.py (the Flask twin) and the
 * web app's own search (web/lib/search.ts): every typed word must start some word of the product's name or brand,
 * in any order, ignoring accents and case. */
export const MIN_QUERY = 2;
export const MAX_QUERY = 60;
export const MAX_WORDS = 6;
export const DEFAULT_LIMIT = 40;
export const MAX_LIMIT = 60;

/** The typed words (lower-case, accent-free, letters and digits only); empty when the query is unusable. */
export function wordsOf(query: string): string[] {
  const text = query
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  if (text.length < MIN_QUERY || text.length > MAX_QUERY) return [];
  return (text.match(/[a-z0-9]+/g) ?? []).slice(0, MAX_WORDS);
}

export function limitOf(raw: string | undefined): number {
  const asked = Number(raw);
  return Number.isInteger(asked) && asked > 0 ? Math.min(asked, MAX_LIMIT) : DEFAULT_LIMIT;
}
