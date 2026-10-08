import { describe, expect, it } from "vitest";
import { ordinary, type Offer, type Product } from "./domain";
import { compareReceipt, nameTokens, receiptSize, type ReceiptItem, type ReceiptResult } from "./receipt";

const now = new Date("2026-10-08T15:00:00Z");

const product = (id: string, name: string, extra: Partial<Product> = {}) =>
  ({ id, name, brand: "", variant: "", category: "Mercearia", subcategory: "", amount: 1000, unit: "ml", pack_count: 1, ...extra }) as Product;

const offer = (productId: string, cents: number, retailer = "Atacadão", extra: Partial<Offer> = {}) =>
  ({
    id: `${productId}-${retailer}-${cents}`,
    product_id: productId,
    retailer_name: retailer,
    price_cents: cents,
    channel: "catalog",
    conditions: ordinary(),
    availability: "available",
    price_observed_at: "2026-10-08T12:00:00Z",
    valid_from: null,
    valid_until: null,
    ttl_hours: 36,
    published: 1,
    ...extra,
  }) as Offer;

const line = (name: string, extra: Partial<ReceiptItem> = {}): ReceiptItem => ({
  line_no: 1,
  name,
  qty: 1,
  unit: "UN",
  unit_price: 5.49,
  discount: null,
  total: 5.49,
  printed_total: 5.49,
  contested: false,
  ...extra,
});

const receipt = (...items: ReceiptItem[]): ReceiptResult => ({
  items,
  flags: { bad_math: [], missing_lines: [], duplicate_lines: [] },
  failed_tiles: [],
  degraded: false,
});

const leite = product("leite", "Leite Integral Italac 1l", { brand: "Italac" });
const catalog = (...products: Product[]) => new Map(products.map((p) => [p.id, p]));
const listOf = (...products: Product[]) => products.map((p) => ({ product_id: p.id }));

function compare(items: ReceiptItem[], products: Product[], offers: Offer[]) {
  return compareReceipt(receipt(...items), listOf(...products), catalog(...products), offers, now);
}

describe("receiptSize / nameTokens", () => {
  it("reads the size a receipt line states, in grams or millilitres", () => {
    expect(receiptSize("LEITE INT ITALAC 1L")).toEqual({ amount: 1000, unit: "ml", packs: 1 });
    expect(receiptSize("ARROZ BCO 500G")).toEqual({ amount: 500, unit: "g", packs: 1 });
    expect(receiptSize("QUEIJO 1,5KG")).toEqual({ amount: 1500, unit: "g", packs: 1 });
    expect(receiptSize("REFRIG GUARANA 12X350ML")).toEqual({ amount: 350, unit: "ml", packs: 12 });
    expect(receiptSize("ABACATE")).toBeNull();
  });

  it("keeps only the words that identify a product", () => {
    expect(nameTokens("LEITE INT ITALAC 1L")).toEqual(["leite", "int", "italac"]);
    expect(nameTokens("Arroz Branco Tipo 1 5kg")).toEqual(["arroz", "branco"]);
    expect(nameTokens("QJO MUSSARELA")).toEqual(["queijo", "mussarela"]);
  });
});

describe("compareReceipt: matching a receipt line to a list item", () => {
  it("matches an abbreviated receipt line to the list item it is", () => {
    const report = compare([line("LEITE INT ITALAC 1L")], [leite], [offer("leite", 549)]);
    expect(report.comparisons).toHaveLength(1);
    expect(report.comparisons[0].productId).toBe("leite");
    expect(report.unmatched).toEqual([]);
  });

  it("does not match when the stated size differs", () => {
    const report = compare([line("LEITE INT ITALAC 500ML")], [leite], [offer("leite", 549)]);
    expect(report.comparisons).toEqual([]);
    expect(report.unmatched).toHaveLength(1);
  });

  it("does not match a single can to a 12-pack, nor a pack with no size to a multipack", () => {
    const pack = product("pack", "Refrigerante Guaraná Antarctica Lata 350ml", { amount: 350, pack_count: 12 });
    expect(compare([line("REFRIG GUARANA ANTARCTICA 350ML")], [pack], [offer("pack", 3000)]).comparisons).toEqual([]);
    expect(compare([line("REFRIG GUARANA ANTARCTICA")], [pack], [offer("pack", 3000)]).comparisons).toEqual([]);
    expect(compare([line("REFRIG GUARANA ANTARCTICA 12X350ML")], [pack], [offer("pack", 3000)]).comparisons).toHaveLength(1);
  });

  it("leaves a line unmatched when two list items explain it equally well", () => {
    const italac = product("italac", "Leite Integral Italac 1l");
    const itambe = product("itambe", "Leite Integral Itambé 1l");
    const report = compare([line("LEITE INTEGRAL 1L")], [italac, itambe], [offer("italac", 549), offer("itambe", 559)]);
    expect(report.comparisons).toEqual([]);
    expect(report.unmatched).toHaveLength(1);
  });

  it("picks the clearly better of two similar list items", () => {
    const italac = product("italac", "Leite Integral Italac 1l");
    const itambe = product("itambe", "Leite Integral Itambé 1l");
    const report = compare([line("LEITE INT ITAMBE 1L")], [italac, itambe], [offer("italac", 549), offer("itambe", 559)]);
    expect(report.comparisons.map((c) => c.productId)).toEqual(["itambe"]);
  });

  it("never matches on a single generic word", () => {
    const arroz = product("arroz", "Arroz Branco Tio João 5kg", { amount: 5000, unit: "g" });
    expect(compare([line("ARROZ 5KG")], [arroz], [offer("arroz", 2490)]).comparisons).toEqual([]);
  });

  it("matches a weighed line only to a product priced per kilo", () => {
    const perKilo = product("abacate", "Abacate Quilo", { amount: 1000, unit: "g" });
    const pack = product("queijo", "Queijo Mussarela Fatiado", { amount: 150, unit: "g" });
    const weighed = line("ABACATE QUILO", { unit: "KG", qty: 0.85, unit_price: 5.99, total: 5.09 });
    expect(compare([weighed], [perKilo], [offer("abacate", 599)]).comparisons).toHaveLength(1);
    const cheese = line("QUEIJO MUSSARELA FATIADO", { unit: "KG", qty: 0.3, unit_price: 49.9, total: 14.97 });
    expect(compare([cheese], [pack], [offer("queijo", 899)]).comparisons).toEqual([]);
  });

  it("matches a weighed line that prints as a single word, as produce does", () => {
    const perKilo = product("abacate", "Abacate Quilo", { amount: 1000, unit: "g" });
    const weighed = line("ABACATE", { unit: "KG", qty: 0.85, unit_price: 5.99, total: 5.09 });
    expect(compare([weighed], [perKilo], [offer("abacate", 599)]).comparisons).toHaveLength(1);
  });

  it("still leaves a weighed single word unmatched when two per-kilo list items fit it equally", () => {
    const plain = product("abacate", "Abacate Quilo", { amount: 1000, unit: "g" });
    const hass = product("hass", "Abacate Hass Quilo", { amount: 1000, unit: "g" });
    const weighed = line("ABACATE", { unit: "KG", qty: 0.85, unit_price: 5.99, total: 5.09 });
    expect(compare([weighed], [plain, hass], [offer("abacate", 599), offer("hass", 899)]).comparisons).toEqual([]);
  });

  it("reports what the list has that the receipt does not, and what the receipt has that the list does not", () => {
    const arroz = product("arroz", "Arroz Branco Tio João 5kg", { amount: 5000, unit: "g" });
    const report = compare([line("LEITE INT ITALAC 1L"), line("CHOCOLATE LACTA 90G")], [leite, arroz], [offer("leite", 549)]);
    expect(report.notOnReceipt).toEqual([{ productId: "arroz", name: "Arroz Branco Tio João 5kg" }]);
    expect(report.unmatched.map((i) => i.name)).toEqual(["CHOCOLATE LACTA 90G"]);
  });

  it("ignores a list line whose product is no longer in the snapshot", () => {
    const report = compareReceipt(receipt(line("LEITE INT ITALAC 1L")), [{ product_id: "gone" }], catalog(), [], now);
    expect(report.comparisons).toEqual([]);
    expect(report.notOnReceipt).toEqual([]);
    expect(report.unmatched).toHaveLength(1);
  });
});

describe("compareReceipt: the price verdict", () => {
  const offers = [offer("leite", 499, "Atacadão"), offer("leite", 629, "Pão de Açúcar")];
  const verdictOf = (price: number) =>
    compare([line("LEITE INT ITALAC 1L", { unit_price: price, total: price })], [leite], offers).comparisons[0];

  it("is inside when the price is within the range of the stores we track", () => {
    expect(verdictOf(5.49).verdict).toBe("inside");
    expect(verdictOf(4.99).verdict).toBe("inside");
    expect(verdictOf(6.29).verdict).toBe("inside");
  });

  it("allows a cent on either bound for rounding", () => {
    expect(verdictOf(4.98).verdict).toBe("inside");
    expect(verdictOf(6.3).verdict).toBe("inside");
  });

  it("is above the highest price we have, or below the lowest (our price may be out of date)", () => {
    expect(verdictOf(7.5).verdict).toBe("above");
    expect(verdictOf(3.99).verdict).toBe("below");
  });

  it("names the cheapest current price and where it is", () => {
    const comparison = verdictOf(5.49);
    expect(comparison.cheapestCents).toBe(499);
    expect(comparison.cheapestRetailer).toBe("Atacadão");
    expect(comparison.highestCents).toBe(629);
  });

  it("has no verdict when we have no current price", () => {
    const stale = offer("leite", 499, "Atacadão", { price_observed_at: "2026-10-01T00:00:00Z" });
    const [comparison] = compare([line("LEITE INT ITALAC 1L")], [leite], [stale]).comparisons;
    expect(comparison.verdict).toBe("no-price");
    expect(comparison.cheapestCents).toBeNull();
  });

  it("does not count a club or coupon price as one anyone can pay", () => {
    const club = offer("leite", 399, "Atacadão", { conditions: { ...ordinary(), club: "Clube" } });
    const [comparison] = compare([line("LEITE INT ITALAC 1L")], [leite], [club, offer("leite", 549, "Pão de Açúcar")]).comparisons;
    expect(comparison.cheapestCents).toBe(549);
  });
});

describe("compareReceipt: what was paid", () => {
  it("uses the price after the line's discount, per unit", () => {
    // 2 x 5,49 with 1,00 off the line: 9,98 for two = 4,99 each
    const discounted = line("LEITE INT ITALAC 1L", { qty: 2, unit_price: 5.49, discount: 1, total: 9.98 });
    const [comparison] = compare([discounted], [leite], [offer("leite", 499)]).comparisons;
    expect(comparison.paidCents).toBe(499);
    expect(comparison.quantity).toBe(2);
  });

  it("falls back to the unit price when a line has no total", () => {
    const noTotal = line("LEITE INT ITALAC 1L", { total: null, printed_total: null, unit_price: 5.49 });
    expect(compare([noTotal], [leite], [offer("leite", 499)]).comparisons[0].paidCents).toBe(549);
  });

  it("is the price per kilo for a weighed item, not the total of the weighing", () => {
    const perKilo = product("abacate", "Abacate Quilo", { amount: 1000, unit: "g" });
    const weighed = line("ABACATE QUILO", { unit: "KG", qty: 0.85, unit_price: 5.99, total: 5.09 });
    expect(compare([weighed], [perKilo], [offer("abacate", 529)]).comparisons[0].paidCents).toBe(599);
  });

  it("totals what was paid above our lowest price, by quantity, and never counts a saving as a loss", () => {
    const arroz = product("arroz", "Arroz Branco Tio João 1kg", { amount: 1000, unit: "g" });
    const items = [
      line("LEITE INT ITALAC 1L", { qty: 2, unit_price: 5.49, total: 10.98 }), // 50c over, twice: 100c
      line("ARROZ BCO TIO JOAO 1KG", { unit_price: 3.5, total: 3.5 }), // cheaper than ours: 0, not -
    ];
    const report = compare(items, [leite, arroz], [offer("leite", 499), offer("arroz", 399)]);
    expect(report.overpaidCents).toBe(100);
  });
});
