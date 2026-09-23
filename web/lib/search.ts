import { clean } from "@/lib/domain";

const words = (text: string) => clean(text).split(/[^a-z0-9]+/).filter(Boolean);
const compact = (text: string) => clean(text).replace(/[^a-z0-9]+/g, "");

/**
 * Whether `text` matches what was typed. Every typed word must start some word of the text, in any
 * order, ignoring accents and case: "abacaxi u" finds "Abacaxi Pérola Unidade", and "unidade aba"
 * does too. A word with digits ("500g") also matches across a space ("500 g"). This is a plain,
 * predictable match (token-prefix), not a typo-tolerant "fuzzy" one - it never guesses.
 */
export function matchesQuery(text: string, query: string): boolean {
  return matchesWords(words(text), compact(text), query);
}

function matchesWords(ownWords: string[], ownCompact: string, query: string): boolean {
  const typed = words(query);
  if (!typed.length) return true;
  return typed.every(
    (word) =>
      ownWords.some((w) => w.startsWith(word)) ||
      (/\d/.test(word) && ownCompact.includes(word)),
  );
}

/** One item with its name (or whatever text is searched) already split into words - see {@link buildIndex}. */
export type SearchIndex<T> = { item: T; words: string[]; compact: string }[];

/**
 * Tokenises every item once, so a search against the same list does not re-clean every name on every
 * keystroke - build it in a `useMemo` keyed on the list (e.g. the loaded products), not inline in a
 * change handler. Typing against a couple of thousand products used to visibly lag because
 * {@link matchesQuery} re-ran `clean()` (Unicode normalisation plus two regexes) on every product's name
 * for every keystroke; here that work happens once, and each search after that only touches the
 * already-split words.
 */
export function buildIndex<T>(items: T[], textOf: (item: T) => string): SearchIndex<T> {
  return items.map((item) => {
    const text = textOf(item);
    return { item, words: words(text), compact: compact(text) };
  });
}

/** The items of a {@link SearchIndex} matching `query`, in their original order (nothing re-sorted, nothing
 * dropped for a limit) - what a results list or a category filter wants. */
export function filterIndexed<T>(index: SearchIndex<T>, query: string): T[] {
  return index.filter((e) => matchesWords(e.words, e.compact, query)).map((e) => e.item);
}

/** The best matches first: names that start with what was typed, then shorter names, then A to Z - what an
 * autocomplete dropdown wants. */
export function searchIndexed<T extends { name: string }>(
  index: SearchIndex<T>,
  query: string,
  limit = 8,
): T[] {
  const first = words(query)[0] ?? "";
  return index
    .filter((e) => matchesWords(e.words, e.compact, query))
    .map((e) => ({ item: e.item, starts: e.words[0]?.startsWith(first) ? 0 : 1 }))
    .sort(
      (a, b) =>
        a.starts - b.starts ||
        a.item.name.length - b.item.name.length ||
        a.item.name.localeCompare(b.item.name, "pt-BR"),
    )
    .slice(0, limit)
    .map(({ item }) => item);
}

/** Convenience for a one-off search against a small, already-in-hand list (tests; short lists that are not
 * searched repeatedly). Anything searched on every keystroke should build a {@link SearchIndex} once with
 * {@link buildIndex} and call {@link searchIndexed} instead. */
export function searchProducts<T extends { name: string }>(
  products: T[],
  query: string,
  limit = 8,
): T[] {
  return searchIndexed(buildIndex(products, (p) => p.name), query, limit);
}
