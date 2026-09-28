import { BRAND, money, unitPrice, type Product } from "./domain";

const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const integer = new Intl.NumberFormat("pt-BR");

/** A count as people read it in Brazil: 4.086, not 4086. */
export const count = (n: number) => integer.format(n);

/** "600 g", "1,5 kg", "18 kg", "350 ml", "2 L" - the catalog stores grams and millilitres. */
export function sizeLabel(amount: number, unit: Product["unit"]): string {
  if (unit === "g") return amount >= 1000 ? `${decimal.format(amount / 1000)} kg` : `${decimal.format(amount)} g`;
  if (unit === "ml") return amount >= 1000 ? `${decimal.format(amount / 1000)} L` : `${decimal.format(amount)} ml`;
  return amount === 1 ? "1 unidade" : `${decimal.format(amount)} unidades`;
}

/**
 * Whether the catalog knows the package at all. A name with no size in it ("Cenoura", "Fralda ... C/30")
 * falls back to one unit (see parse_size in services/public_api.py), which says nothing about the pack.
 */
export const knownSize = (p: Pick<Product, "amount" | "unit" | "pack_count">) =>
  !(p.unit === "un" && p.amount * p.pack_count === 1);

/** The package as shown next to a product: "12 × 350 ml", "48 unidades", "Tamanho não informado". */
export function packLabel(p: Pick<Product, "amount" | "unit" | "pack_count" | "variant">): string {
  let size: string;
  if (!knownSize(p)) size = "Tamanho não informado";
  else if (p.unit === "un") size = sizeLabel(p.amount * p.pack_count, "un");
  else size = p.pack_count > 1 ? `${p.pack_count} × ${sizeLabel(p.amount, p.unit)}` : sizeLabel(p.amount, p.unit);
  return p.variant ? `${p.variant} · ${size}` : size;
}

/**
 * The per-kg/L/unit price that makes different packs comparable, or null when it would mislead: an unknown
 * pack (one "unit" by default), or - unless `repeat` - a pack of exactly one kg/L/unit, where it only repeats
 * the price (a list of sizes side by side sets `repeat`, so every row has the same comparable figure).
 */
export function unitPriceText(
  p: Pick<Product, "amount" | "unit" | "pack_count">,
  cents: number,
  { repeat = false } = {},
): string | null {
  if (!knownSize(p)) return null;
  const up = unitPrice(p as Product, cents);
  if (up.value === cents && !repeat) return null;
  return `${money(up.value)}/${up.unit}`;
}

/** "Preço do site", "Preço de loja física", "Preço de encarte": where the price was seen. */
export function channelLabel(channel: "catalog" | "physical" | "flyer"): string {
  return channel === "catalog" ? "Preço do site" : channel === "physical" ? "Preço de loja física" : "Preço de encarte";
}

const dayKey = (d: Date) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: BRAND.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);

/** "hoje às 12:03", "ontem às 18:00", "em 25/09 às 12:03" - in Fortaleza time. */
export function whenLabel(iso: string, now = new Date()): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return "em data não informada";
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone: BRAND.timezone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  if (dayKey(date) === dayKey(now)) return `hoje às ${time}`;
  if (dayKey(date) === dayKey(new Date(now.getTime() - 86400000))) return `ontem às ${time}`;
  const day = new Intl.DateTimeFormat("pt-BR", {
    timeZone: BRAND.timezone,
    day: "2-digit",
    month: "2-digit",
  }).format(date);
  return `em ${day} às ${time}`;
}

/** The name kept in a shopping-list line: the product name, plus the pack only when the name lacks it. */
export function listName(p: Pick<Product, "name" | "brand" | "amount" | "unit" | "pack_count" | "variant">): string {
  const lower = p.name.toLowerCase();
  const parts = [p.name];
  if (p.brand && !lower.includes(p.brand.toLowerCase())) parts.push(p.brand);
  if (knownSize(p) && !/\d/.test(p.name)) parts.push(packLabel(p));
  return parts.join(" · ");
}
