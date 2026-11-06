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

  it("splits a size glued to the words around it, but leaves short numbers in a word alone", () => {
    expect(nameTokens("SUPLEN JUNGLE500TANG")).toEqual(["suplen", "jungle", "tang"]);
    expect(nameTokens("SUPLEN LOW JUNGLE500")).toEqual(["suplen", "low", "jungle"]);
    expect(nameTokens("VITAMINA B12 BAYER")).toEqual(["vitamina", "b12", "bayer"]);
    expect(nameTokens("REFRIG 7UP")).toEqual(["refrigerante", "7up"]);
  });

  it("reads a size printed without its unit when it is glued to a word", () => {
    expect(receiptSize("SUPLEN JUNGLE500TANG")).toEqual({ amount: 500, unit: null, packs: 1 });
    expect(receiptSize("VITAMINA B12 BAYER")).toBeNull();
  });
});

describe("compareReceipt: a size glued to the name ('SUPLEN JUNGLE500TANG')", () => {
  const tang = product("tang", "Suplemento Alimentar Jungle Organico Endurance Tangerina 500ml", { amount: 500 });
  const morango = product("mor", "Suplemento Alimentar Jungle Organico Low Carb Morango Com Limao 500ml", { amount: 500 });
  const uva = product("uva", "Suplemento Alimentar Jungle Organico Low Carb Uva 500ml", { amount: 500 });
  const stick = product("stick", "Suplemento Alimentar Em Po Jungle Plant Power Tangerina E Morango 5g Stick", { amount: 5, unit: "g" });
  const products = [tang, morango, uva, stick];
  const offers = products.map((p) => offer(p.id, 749, "Pinheiro Supermercado"));
  const printed = (name: string) => line(name, { unit_price: 8.49, discount: 2, total: 6.49, printed_total: 6.49 });

  it("matches the flavour it names, and only among the products of that size", () => {
    const report = compare([printed("SUPLEN JUNGLE500TANG"), printed("SUPLEN JUNGLE500MOR")], products, offers);
    expect(report.comparisons.map((c) => c.productId)).toEqual(["tang", "mor"]); // not the 5 g stick that also says "Tangerina"
    expect(report.unmatched).toHaveLength(0);
  });

  it("still leaves a line that names no flavour unmatched when several flavours fit it equally", () => {
    const report = compare([printed("SUPLEN LOW JUNGLE500")], products, offers);
    expect(report.comparisons).toHaveLength(0);
    expect(report.unmatched).toHaveLength(1); // only the barcode can tell Morango from Uva: never guessed
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
    expect(compare([weighed], [plain, hass], [offer("abacate", 599), offer("hass", 605)]).comparisons).toEqual([]);
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

const GTIN = "7894900011517";
const coded = (id: string, name: string, extra: Partial<Product> = {}) => product(id, name, { gtin: GTIN, gtin_evidence: "loja", ...extra });

describe("compareReceipt: the barcode a line prints", () => {
  it("recognises the product by its barcode whatever the name says", () => {
    const coke = coded("coke", "Refrigerante Coca-Cola Original 2l", { brand: "Coca-Cola" });
    const report = compare([line("QQ XYZ 123", { code: GTIN })], [coke], [offer("coke", 999)]);
    expect(report.comparisons).toMatchObject([{ productId: "coke", via: "code", onList: true }]);
  });

  it("settles what the name leaves tied between two list items", () => {
    const italac = coded("italac", "Leite Integral Italac 1l");
    const itambe = product("itambe", "Leite Integral Itambé 1l", { gtin: "7891000100103", gtin_evidence: "loja" });
    const report = compare([line("LEITE INTEGRAL 1L", { code: GTIN })], [italac, itambe], [offer("italac", 549), offer("itambe", 559)]);
    expect(report.comparisons.map((c) => c.productId)).toEqual(["italac"]);
  });

  it("finds it though the receipt pads the barcode with zeros", () => {
    const coke = coded("coke", "Refrigerante Coca-Cola Original 2l");
    const report = compare([line("X", { code: `0${GTIN}` })], [coke], [offer("coke", 999)]);
    expect(report.comparisons).toHaveLength(1);
  });

  it("looks outside the list only when asked, and says the product was not on it", () => {
    const coke = coded("coke", "Refrigerante Coca-Cola Original 2l");
    const read = receipt(line("X", { code: GTIN }));
    const offers = [offer("coke", 999)];
    expect(compareReceipt(read, [], catalog(coke), offers, now).unmatched).toHaveLength(1);
    expect(compareReceipt(read, [], catalog(coke), offers, now, "catalogue").comparisons).toMatchObject([{ productId: "coke", via: "code", onList: false }]);
  });

  it("falls back to the name when the code is not one we know", () => {
    const report = compare([line("LEITE INT ITALAC 1L", { code: "7890000000008" })], [leite], [offer("leite", 549)]);
    expect(report.comparisons).toMatchObject([{ productId: "leite", via: "name" }]);
  });
});

describe("compareReceipt: names cut short or abbreviated", () => {
  const queijo = product("queijo", "Queijo Mussarela Fatiado Tirolez 150g", { amount: 150, unit: "g", brand: "Tirolez" });
  it("reads QJ as queijo and a clipped word as the start of the real one", () => {
    const report = compare([line("QJ MUSS FAT TIROLEZ 150G")], [queijo], [offer("queijo", 899)]);
    expect(report.comparisons).toHaveLength(1);
  });

  it("forgives one misread letter in a long word", () => {
    const report = compare([line("QJ MUSSARELA FATIADO TIROLEZ 150G".replace("TIROLEZ", "TIROLES"))], [queijo], [offer("queijo", 899)]);
    expect(report.comparisons).toHaveLength(1);
  });

  it("does not take a different product for it", () => {
    const report = compare([line("QJ PARM RALADO SADIA 150G")], [queijo], [offer("queijo", 899)]);
    expect(report.comparisons).toEqual([]);
  });

  it("uses the price paid to tell sizes apart when the name cuts off before the size", () => {
    const small = product("small", "Refrigerante Coca Cola Original 600ml", { brand: "Coca-Cola", amount: 600 });
    const big = product("big", "Refrigerante Coca Cola Original 2,5l", { brand: "Coca-Cola", amount: 2500 });
    const offers = [offer("small", 699), offer("big", 1299)];
    const at = (total: number) =>
      compare([line("REF COCA COLA ORIGIN", { unit_price: total, total })], [small, big], offers).comparisons.map((c) => c.productId);
    expect(at(12.99)).toEqual(["big"]);
    expect(at(6.99)).toEqual(["small"]);
    expect(at(9.5)).toEqual([]); // fits neither clearly
  });

  it("will not pick between packs of different brands by price alone", () => {
    const a = product("a", "Leite Integral Italac 1l", { brand: "Italac" });
    const b = product("b", "Leite Integral Itambé 1l", { brand: "Itambé" });
    expect(compare([line("LEITE INTEGRAL 1L")], [a, b], [offer("a", 549), offer("b", 549)]).comparisons).toEqual([]);
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
