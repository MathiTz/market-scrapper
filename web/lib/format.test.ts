import { describe, expect, it } from "vitest";
import type { Product } from "./domain";
import { count, knownSize, listName, packLabel, sizeLabel, unitPriceText, whenLabel } from "./format";

const product = (p: Partial<Product>) =>
  ({ name: "Produto", brand: "", variant: "", amount: 1, unit: "un", pack_count: 1, ...p }) as Product;

describe("sizeLabel and packLabel", () => {
  it("reads grams and millilitres the way packs are labelled", () => {
    expect(sizeLabel(600, "g")).toBe("600 g");
    expect(sizeLabel(18000, "g")).toBe("18 kg");
    expect(sizeLabel(1250, "g")).toBe("1,25 kg");
    expect(sizeLabel(350, "ml")).toBe("350 ml");
    expect(sizeLabel(1500, "ml")).toBe("1,5 L");
    expect(sizeLabel(2000, "ml")).toBe("2 L");
  });

  it("shows multipacks and unit counts", () => {
    expect(packLabel(product({ amount: 350, unit: "ml", pack_count: 12 }))).toBe("12 × 350 ml");
    expect(packLabel(product({ amount: 1, unit: "un", pack_count: 48 }))).toBe("48 unidades");
    expect(packLabel(product({ amount: 1000, unit: "g", variant: "Tipo 1" }))).toBe("Tipo 1 · 1 kg");
  });

  it("does not invent a size the catalog does not have", () => {
    const unknown = product({ amount: 1, unit: "un", pack_count: 1 });
    expect(knownSize(unknown)).toBe(false);
    expect(packLabel(unknown)).toBe("Tamanho não informado");
  });
});

describe("unitPriceText", () => {
  it("gives the per-kg/L price that makes packs comparable", () => {
    // Intl separates "R$" from the amount with a no-break space.
    expect(unitPriceText(product({ amount: 600, unit: "g" }), 1648)).toBe("R$ 27,47/kg");
    expect(unitPriceText(product({ amount: 350, unit: "ml", pack_count: 12 }), 4200)).toBe("R$ 10,00/L");
  });

  it("stays silent when it would only repeat the price or when the pack is unknown", () => {
    expect(unitPriceText(product({ amount: 1000, unit: "g" }), 799)).toBeNull();
    expect(unitPriceText(product({ amount: 1, unit: "un" }), 599)).toBeNull();
  });
});

describe("whenLabel", () => {
  const now = new Date("2026-09-27T18:00:00-03:00");
  it("says today and yesterday in Fortaleza time", () => {
    expect(whenLabel("2026-09-27T15:03:04Z", now)).toBe("hoje às 12:03");
    expect(whenLabel("2026-09-26T21:00:00Z", now)).toBe("ontem às 18:00");
    expect(whenLabel("2026-09-20T15:00:00Z", now)).toBe("em 20/09 às 12:00");
  });

  it("does not break on a missing date", () => {
    expect(whenLabel("", now)).toBe("em data não informada");
  });
});

describe("count and listName", () => {
  it("formats thousands in pt-BR", () => {
    expect(count(4086)).toBe("4.086");
  });

  it("adds the brand and pack only when the name lacks them", () => {
    expect(listName(product({ name: "Lasanha Bolonhesa Sadia Pacote 600g", brand: "Sadia", amount: 600, unit: "g" }))).toBe(
      "Lasanha Bolonhesa Sadia Pacote 600g",
    );
    expect(listName(product({ name: "Arroz branco", brand: "Marca Exemplo", amount: 1000, unit: "g" }))).toBe(
      "Arroz branco · Marca Exemplo · 1 kg",
    );
    expect(listName(product({ name: "Cenoura", amount: 1, unit: "un" }))).toBe("Cenoura");
  });
});
