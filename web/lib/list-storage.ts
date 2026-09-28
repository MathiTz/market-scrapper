/** One line of the shopping list, as kept in this browser's localStorage (keys med-list-real / med-list-demo). */
export type Line = { product_id: string; name: string; quantity: number };

/**
 * What went wrong with the saved list, if anything:
 * - blocked: the browser refuses local storage (private mode, blocked site data) - nothing can be kept;
 * - unreadable: the saved value could not be read at all; a copy of it was kept before starting over;
 * - partial: some saved lines were invalid and left out; a copy of the original value was kept;
 * - save-failed: writing the list failed (storage full or refused).
 */
export type StorageIssue = "blocked" | "unreadable" | "partial" | "save-failed" | null;

type Store = Pick<Storage, "getItem" | "setItem">;

export const MAX_LINES = 200;
export const MAX_QUANTITY = 999;

/** The browser's localStorage, or null when merely touching it throws (some privacy settings do). */
export function browserStorage(): Store | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function validLine(x: unknown): x is Line {
  if (!x || typeof x !== "object") return false;
  const l = x as Record<string, unknown>;
  return (
    typeof l.product_id === "string" &&
    l.product_id.length > 0 &&
    l.product_id.length <= 200 &&
    Number.isInteger(l.quantity) &&
    (l.quantity as number) > 0 &&
    (l.quantity as number) <= MAX_QUANTITY
  );
}

/**
 * Where a copy of an unreadable saved value is kept: named after the value itself, so reading the same bad
 * value twice (React runs effects twice in development) keeps one copy, and a different one gets its own.
 */
export function copyKey(key: string, raw: string) {
  let hash = 5381;
  for (let i = 0; i < raw.length; i++) hash = ((hash * 33) ^ raw.charCodeAt(i)) >>> 0;
  return `${key}-copia-${hash.toString(36)}`;
}

/** Keeps the saved text under another key before anything overwrites it, so a list is never lost silently. */
function keepCopy(storage: Store, key: string, raw: string) {
  try {
    storage.setItem(copyKey(key, raw), raw);
  } catch {
    // Nothing else can be done here; the original value stays untouched until the next save.
  }
}

/** The saved list and whatever went wrong reading it. Never throws. */
export function readList(storage: Store | null, key: string): { lines: Line[]; issue: StorageIssue } {
  if (!storage) return { lines: [], issue: "blocked" };
  let raw: string | null;
  try {
    raw = storage.getItem(key);
  } catch {
    return { lines: [], issue: "blocked" };
  }
  if (raw === null || raw === "") return { lines: [], issue: null };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    keepCopy(storage, key, raw);
    return { lines: [], issue: "unreadable" };
  }
  if (!Array.isArray(parsed)) {
    keepCopy(storage, key, raw);
    return { lines: [], issue: "unreadable" };
  }
  const lines = parsed.filter(validLine).slice(0, MAX_LINES).map((l) => ({
    product_id: l.product_id,
    name: typeof l.name === "string" && l.name.trim() ? l.name : "Item salvo",
    quantity: l.quantity,
  }));
  if (lines.length < parsed.length) {
    keepCopy(storage, key, raw);
    return { lines, issue: "partial" };
  }
  return { lines, issue: null };
}

/** Saves the list; false when the browser refused. */
export function writeList(storage: Store | null, key: string, lines: Line[]): boolean {
  if (!storage) return false;
  try {
    storage.setItem(key, JSON.stringify(lines));
    return true;
  } catch {
    return false;
  }
}

/** What to tell the person about a storage issue, or null when there is none. */
export function storageMessage(issue: StorageIssue): string | null {
  switch (issue) {
    case "blocked":
      return "Este navegador não permite guardar dados neste site. A lista funciona enquanto a página estiver aberta, mas não será mantida ao fechar ou recarregar.";
    case "unreadable":
      return "Não foi possível ler a lista salva anteriormente neste navegador. Guardamos uma cópia do conteúdo original neste aparelho e começamos uma lista nova.";
    case "partial":
      return "Alguns itens salvos anteriormente não puderam ser lidos e ficaram de fora. Guardamos uma cópia do conteúdo original neste aparelho.";
    case "save-failed":
      return "Não foi possível salvar a última alteração da lista neste navegador. Os itens continuam aqui enquanto a página estiver aberta.";
    default:
      return null;
  }
}
