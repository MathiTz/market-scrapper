import { describe, expect, it } from "vitest";
import { ordinary, type Offer, type Product } from "./domain";
import { compareBasket } from "./receipt-basket";
import type { ReceiptComparison, ReceiptItem } from "./receipt";

const now = new Date("2026-10-08T15:00:00Z");

const product = (id: string, name: string, extra: Partial<Product> = {}) =>
  ({ id, name, brand: "", variant: "", category: "Mercearia", subcategory: "Arroz", amount: 1000, unit: "g", pack_count: 1, ...extra }) as Product;

const offer = (productId: string, cents: number, retailer = "Atacadão", extra: Partial<Offer> = {}) =>
  ({
    id: `${productId}-${retailer}-${cents}`,
    product_id: productId,
    retailer_id: retailer,
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

const bought = (p: Product, paidCents: number | null, quantity = 1): ReceiptComparison => ({
  item: { name: p.name } as ReceiptItem,
  productId: p.id,
  productName: p.name,
  via: "name",
  onList: true,
  paidCents,
  quantity,
  cheapestCents: null,
  cheapestRetailer: null,
  highestCents: null,
  verdict: "no-price",
});

const catalog = (...products: Product[]) => new Map(products.map((p) => [p.id, p]));

// Bought: 1 kg of rice for R$ 5,50.
const rice = product("rice", "Arroz Agulhinha Tipo 1 Camil 1kg", { brand: "Camil" });

describe("compareBasket: one barcode named differently", () => {
  it("counts another chain's listing of the same barcode as the same product", () => {
    const gtin = { gtin: "7891234567895", gtin_evidence: "loja" };
    const mine = product("mine", "Arroz Agulhinha Camil 1kg", gtin);
    const theirs = product("theirs", "Arroz Camil Tipo 1 Pacote 1kg", gtin);
    const report = compareBasket(
      [bought(mine, 550)],
      catalog(mine, theirs),
      [offer("mine", 520, "Atacadão"), offer("theirs", 489, "Pinheiro")],
      now,
    );
    const pinheiro = report.chains.find((c) => c.retailerName === "Pinheiro")!;
    expect([pinheiro.lines[0].kind, pinheiro.lines[0].product.id, pinheiro.totalCents]).toEqual(["same", "theirs", 489]);
  });
});

describe("compareBasket: the same product", () => {
  it("prices the line at every chain that sells it, and sums what was paid beside it", () => {
    const report = compareBasket(
      [bought(rice, 550, 2)],
      catalog(rice),
      [offer("rice", 499, "Atacadão"), offer("rice", 589, "Pinheiro")],
      now,
    );
    const [first, second] = report.chains;
    expect([first.retailerName, first.totalCents, first.paidCents]).toEqual(["Atacadão", 998, 1100]);
    expect([second.retailerName, second.totalCents]).toEqual(["Pinheiro", 1178]);
    expect(report.bestSingle?.retailerName).toBe("Atacadão");
    expect(report.bestSplit).toMatchObject({ totalCents: 998, paidCents: 1100, lines: 1 });
    expect(first.lines[0].kind).toBe("same");
  });

  it("ignores stale prices and club or coupon prices", () => {
    const report = compareBasket(
      [bought(rice, 550)],
      catalog(rice),
      [
        offer("rice", 100, "Velho", { price_observed_at: "2026-09-01T12:00:00Z" }),
        offer("rice", 100, "Clube", { conditions: { ...ordinary(), club: "Clube" } }),
        offer("rice", 520, "Pinheiro"),
      ],
      now,
    );
    expect(report.chains.map((c) => c.retailerName)).toEqual(["Pinheiro"]);
  });

  it("skips a receipt line with no price paid", () => {
    const report = compareBasket([bought(rice, null)], catalog(rice), [offer("rice", 499)], now);
    expect(report.considered).toBe(0);
    expect(report.chains).toEqual([]);
    expect(report.bestSplit).toBeNull();
  });
});

describe("compareBasket: a similar product, by price per kg", () => {
  // The other chain only sells the same kind of rice in a 5 kg bag: R$ 18,99 = R$ 3,80/kg.
  const bag = product("bag", "Arroz Agulhinha Tipo 1 Extremo Sul 5kg", { brand: "Extremo Sul", amount: 5000 });

  it("scales its price to the amount bought and keeps the pack price", () => {
    const report = compareBasket(
      [bought(rice, 550, 2)], // 2 kg bought
      catalog(rice, bag),
      [offer("rice", 589, "Pinheiro"), offer("bag", 1899, "Atacadão")],
      now,
    );
    const atacadao = report.chains.find((c) => c.retailerName === "Atacadão")!;
    expect(atacadao.lines[0]).toMatchObject({ kind: "similar", packCents: 1899, costCents: 760 }); // 3,80 x 2 kg
    expect(atacadao.lines[0].product.id).toBe("bag");
    expect(report.bestSingle?.retailerName).toBe("Atacadão");
  });

  it("prefers the product itself over a similar one at the same chain", () => {
    const report = compareBasket(
      [bought(rice, 550)],
      catalog(rice, bag),
      [offer("rice", 589, "Atacadão"), offer("bag", 1499, "Atacadão")],
      now,
    );
    expect(report.chains[0].lines[0]).toMatchObject({ kind: "same", costCents: 589 });
  });

  it("does not take pet food that merely mentions rice", () => {
    const dog = product("dog", "Ração Cães Dog Chow Cordeiro e Arroz 1kg", { brand: "Dog Chow" });
    const report = compareBasket([bought(rice, 550)], catalog(rice, dog), [offer("dog", 480, "Atacadão")], now);
    expect(report.chains).toEqual([]);
  });

  it("does not match across tags, or across a weight and a volume", () => {
    const other = product("o", "Arroz Agulhinha Tipo 1 Importado 1l", { unit: "ml" });
    const wrongTag = product("t", "Arroz Agulhinha Tipo 1 Outro 1kg", { subcategory: "Feijao" });
    const report = compareBasket(
      [bought(rice, 550)],
      catalog(rice, other, wrongTag),
      [offer("o", 400, "A"), offer("t", 400, "B")],
      now,
    );
    expect(report.chains).toEqual([]);
  });

  it("does not match on a single shared word", () => {
    const plain = product("plain", "Arroz 1kg");
    const cousin = product("cousin", "Arroz Parboilizado 1kg");
    const report = compareBasket([bought(plain, 500)], catalog(plain, cousin), [offer("cousin", 400)], now);
    expect(report.chains).toEqual([]); // "arroz" alone names the whole aisle
  });

  it("drops a price per kilo far from what was paid", () => {
    const capsule = product("cap", "Arroz Agulhinha Tipo 1 Cápsula 10g", { amount: 10 });
    const report = compareBasket([bought(rice, 550)], catalog(rice, capsule), [offer("cap", 2190, "Atacadão")], now);
    expect(report.chains).toEqual([]); // R$ 219/kg against R$ 5,50/kg
  });
});

describe("compareBasket: coverage and splitting", () => {
  const beans = product("beans", "Feijao Carioca Tipo 1 Camil 1kg", { subcategory: "Feijao", brand: "Camil" });

  it("puts a chain that lacks a line behind the ones that have everything, and names what is missing", () => {
    const report = compareBasket(
      [bought(rice, 550), bought(beans, 800)],
      catalog(rice, beans),
      [
        offer("rice", 400, "Barato"), // only rice, very cheap
        offer("rice", 520, "Completo"),
        offer("beans", 780, "Completo"),
      ],
      now,
    );
    expect(report.chains.map((c) => c.retailerName)).toEqual(["Completo", "Barato"]);
    expect(report.bestSingle?.retailerName).toBe("Completo");
    const partial = report.chains[1];
    expect(partial.missing.map((m) => m.productId)).toEqual(["beans"]);
    expect(partial.paidCents).toBe(550); // paid is only for the lines it covers
  });

  it("splits the list across the cheapest chain for each line", () => {
    const report = compareBasket(
      [bought(rice, 550), bought(beans, 800)],
      catalog(rice, beans),
      [offer("rice", 400, "A"), offer("beans", 900, "A"), offer("rice", 600, "B"), offer("beans", 700, "B")],
      now,
    );
    expect(report.bestSplit).toMatchObject({ totalCents: 1100, paidCents: 1350, lines: 2 });
    expect(report.bestSplit!.chains.sort()).toEqual(["A", "B"]);
  });

  it("has no single best chain when none has every line", () => {
    const report = compareBasket(
      [bought(rice, 550), bought(beans, 800)],
      catalog(rice, beans),
      [offer("rice", 400, "A"), offer("beans", 700, "B")],
      now,
    );
    expect(report.bestSingle).toBeNull();
    expect(report.bestSplit).toMatchObject({ totalCents: 1100, lines: 2 });
  });
});
