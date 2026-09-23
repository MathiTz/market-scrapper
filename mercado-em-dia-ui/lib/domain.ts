import { z } from "zod";
export const BRAND = {
  name: "Mercado em Dia",
  city: "Fortaleza",
  timezone: "America/Fortaleza",
};
export const clean = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
export function cents(s: string): number {
  const v = s.replace(/^R\$\s*/, "").trim();
  if (!/^(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}$/.test(v))
    throw Error("Use reais com duas casas decimais, ex.: 12,90.");
  const n = Number(v.replace(/\./g, "").replace(",", ""));
  if (!Number.isSafeInteger(n) || n <= 0)
    throw Error("Preço deve ser positivo.");
  return n;
}
export const money = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    n / 100,
  );
export function normalizeUnit(amount: number, unit: string) {
  if (!Number.isFinite(amount) || amount <= 0) throw Error("Conteúdo inválido");
  const u = unit.toLowerCase();
  if (!["kg", "g", "l", "ml", "un"].includes(u))
    throw Error("Unidade inválida");
  return {
    amount: Math.round(amount * (u === "kg" || u === "l" ? 1000 : 1)),
    unit: u === "kg" ? "g" : u === "l" ? "ml" : u,
  };
}
const text = z.string().trim().min(1).max(200);
export const productSchema = z
  .object({
    id: z.string().optional(),
    name: text,
    brand: text,
    category: text,
    // A finer type than category ("Hidratante", "Sabonete" instead of one shared "Higiene e beleza") -
    // empty when the ETL found nothing specific enough to name a kind of product (see subcategorize() in
    // services/public_api.py), unlike category, which always resolves to at least "Outros".
    subcategory: z.string().max(200).default(""),
    variant: text,
    amount: z.number().int().positive().max(1000000),
    unit: z.enum(["g", "ml", "un"]),
    pack_count: z.number().int().min(1).max(1000),
    gtin: z
      .string()
      .regex(/^(?:\d{8}|\d{12}|\d{13}|\d{14})$/)
      .nullable()
      .default(null),
    gtin_evidence: z.string().max(1000).nullable().default(null),
  })
  .refine(
    (p) => !p.gtin || !!p.gtin_evidence,
    "GTIN requer evidência verificada.",
  );
export type Product = z.infer<typeof productSchema> & {
  id: string;
  image_url?: string | null;
  image_source_url?: string | null;
};
export const conditionsSchema = z.object({
  club: z.string().max(100).nullable().default(null),
  coupon: z.string().max(100).nullable().default(null),
  min_quantity: z.number().int().min(1).default(1),
  limit_per_customer: z.number().int().positive().nullable().default(null),
  payment: z.string().max(100).nullable().default(null),
  region_note: z.string().max(300).default(""),
});
export type Conditions = z.infer<typeof conditionsSchema>;
export const ordinary = (): Conditions => ({
  club: null,
  coupon: null,
  min_quantity: 1,
  limit_per_customer: null,
  payment: null,
  region_note: "",
});
export const isConditional = (c: Conditions) =>
  !!(c.club || c.coupon || c.min_quantity > 1 || c.payment);
export function conditionLabel(c: Conditions) {
  return (
    [
      c.club && `Clube ${c.club}`,
      c.coupon && `Cupom ${c.coupon}`,
      c.min_quantity > 1 && `Mínimo ${c.min_quantity} un.`,
      c.limit_per_customer && `Limite ${c.limit_per_customer} por cliente`,
      c.payment && `Pagamento: ${c.payment}`,
      c.region_note,
    ]
      .filter(Boolean)
      .join(" · ") || "Sem condição especial"
  );
}
export type Offer = {
  id: string;
  product_id: string;
  retailer_id: string;
  retailer_name: string;
  context_id: string;
  context_label: string;
  /** A chain has several real branches, not one address - see `retailer_locations` in the snapshot and
   * `offerLocation` in lib/location.ts, which resolves the nearest one to wherever the person is looking. */
  store_phone?: string | null;
  channel: "catalog" | "physical" | "flyer";
  price_cents: number | null;
  regular_price_cents?: number | null;
  deal_label?: string | null;
  currency: string;
  conditions: Conditions;
  availability: "available" | "unavailable" | "unknown";
  /** Units the store says it has, when it says (informational). */
  stock?: number | null;
  price_observed_at: string;
  source_checked_at: string | null;
  valid_from: string | null;
  valid_until: string | null;
  collected_at: string;
  source_url: string;
  method: "manual" | "automatic" | "demo";
  published: number;
  ttl_hours: number;
  collection_error?: string | null;
};
export const offerSchema = z
  .object({
    product_id: text,
    retailer_id: text,
    context_id: text,
    channel: z.enum(["catalog", "physical", "flyer"]),
    price_cents: z.number().int().positive().max(100000000).nullable(),
    conditions: conditionsSchema,
    availability: z.enum(["available", "unavailable", "unknown"]),
    price_observed_at: z.iso.datetime(),
    valid_from: z.iso.datetime().nullable(),
    valid_until: z.iso.datetime().nullable(),
    source_url: z.url().max(2000),
    evidence: text,
  })
  .superRefine((o, c) => {
    if (o.price_cents === null && o.availability !== "unavailable")
      c.addIssue({
        code: "custom",
        message: "Preço ausente: mantenha na revisão.",
      });
    if (o.channel === "flyer" && (!o.valid_from || !o.valid_until))
      c.addIssue({ code: "custom", message: "Encarte exige início e fim." });
    if (o.valid_from && o.valid_until && o.valid_from >= o.valid_until)
      c.addIssue({ code: "custom", message: "Validade invertida." });
    if (Date.parse(o.price_observed_at) > Date.now() + 60000)
      c.addIssue({
        code: "custom",
        message: "Observação não pode ser futura.",
      });
  });
export function signature(
  p: Pick<
    Product,
    "name" | "brand" | "category" | "variant" | "amount" | "unit" | "pack_count"
  >,
) {
  return [
    p.name,
    p.brand,
    p.category,
    p.variant,
    p.amount,
    p.unit,
    p.pack_count,
  ]
    .map((x) => clean(String(x)))
    .join("|");
}
export function exactMatch(a: Product, b: Product) {
  if (a.gtin && b.gtin && a.gtin !== b.gtin) return false;
  return signature(a) === signature(b);
}
export function offerState(o: Offer, now = new Date()) {
  const t = now.getTime();
  if (o.valid_from && Date.parse(o.valid_from) > t) return "future";
  if (o.valid_until && Date.parse(o.valid_until) < t) return "expired";
  if (
    o.channel !== "flyer" &&
    t - Date.parse(o.price_observed_at) > o.ttl_hours * 3600000
  )
    return "stale";
  if (o.availability === "unavailable") return "unavailable";
  return "current";
}
export function rankOffers(
  offers: Offer[],
  includeConditions = false,
  now = new Date(),
) {
  return offers
    .filter(
      (o) =>
        o.published === 1 &&
        o.price_cents !== null &&
        offerState(o, now) === "current" &&
        (includeConditions || !isConditional(o.conditions)),
    )
    .sort((a, b) => a.price_cents! - b.price_cents!);
}
export function unitPrice(p: Product, price: number) {
  return {
    value: Math.round(
      (price / (p.amount * p.pack_count)) * (p.unit === "un" ? 1 : 1000),
    ),
    unit: p.unit === "g" ? "kg" : p.unit === "ml" ? "L" : "un.",
  };
}
export type BasketItem = {
  product_id: string;
  quantity: number;
  /** The offer this store gives for the item, or null when it has no current price for it. */
  offer: Offer | null;
};
export function basket(
  lines: { product_id: string; quantity: number }[],
  offers: Offer[],
  now = new Date(),
) {
  const contexts = [...new Set(offers.map((o) => o.context_id))];
  return contexts
    .map((id) => {
      let covered = 0,
        total = 0;
      const items: BasketItem[] = [];
      for (const l of lines) {
        const o = rankOffers(
          offers.filter(
            (o) => o.context_id === id && o.product_id === l.product_id,
          ),
          false,
          now,
        ).find(
          (o) =>
            !o.conditions.limit_per_customer ||
            l.quantity <= o.conditions.limit_per_customer,
        );
        items.push({
          product_id: l.product_id,
          quantity: l.quantity,
          offer: o ?? null,
        });
        if (o) {
          covered++;
          total += o.price_cents! * l.quantity;
        }
      }
      return {
        context_id: id,
        covered,
        total,
        complete: covered === lines.length && lines.length > 0,
        items,
      };
    })
    .sort(
      (a, b) =>
        Number(b.complete) - Number(a.complete) ||
        (a.complete ? a.total - b.total : b.covered - a.covered),
    );
}
export const localTime = (s: string) =>
  new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: BRAND.timezone,
  }).format(new Date(s));
export type Flyer = {
  id: string;
  retailer_id: string;
  retailer_name?: string;
  title: string;
  source_url: string;
  media_url?: string | null;
  media_type?: "image" | "pdf" | null;
  media_pages?: string[];
  valid_from: string | null;
  valid_until: string | null;
  scope: string;
  version_hash: string;
  collected_at: string;
  source_checked_at: string | null;
  method: string;
  status: string;
  published: number;
};
export function flyerState(f: Flyer, now = new Date()) {
  const from = f.valid_from ? Date.parse(f.valid_from) : NaN;
  const until = f.valid_until ? Date.parse(f.valid_until) : NaN;
  if (!Number.isFinite(from) || !Number.isFinite(until) || from > until)
    return "unknown";
  if (now.getTime() < from) return "future";
  return now.getTime() > until ? "expired" : "current";
}
