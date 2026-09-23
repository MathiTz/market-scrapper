import { describe, expect, it } from "vitest";
import { stockNote } from "./stock";

describe("stockNote", () => {
  it("states the stock the store reports, as information", () => {
    expect(stockNote({ stock: 179 })).toBe("Estoque informado pela loja: 179 unidades");
    expect(stockNote({ stock: 1 })).toBe("Estoque informado pela loja: 1 unidade");
    expect(stockNote({ stock: 1200 })).toBe("Estoque informado pela loja: 1.200 unidades");
  });

  it("says nothing without a real number", () => {
    for (const stock of [null, undefined, 0, -3, Number.NaN]) expect(stockNote({ stock })).toBeNull();
  });

  it("never uses scarcity wording, whatever the number", () => {
    for (const stock of [1, 2, 8, 500]) expect(stockNote({ stock })).not.toMatch(/só|apenas|restam|últimas/i);
  });
});
