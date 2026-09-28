import { describe, expect, it } from "vitest";
import { conditionLabel, ordinary } from "./domain";

describe("conditionLabel", () => {
  it("says a club price is only for members, without repeating the word", () => {
    expect(conditionLabel({ ...ordinary(), club: "PinClube" })).toBe("Só para membros do PinClube");
    expect(conditionLabel({ ...ordinary(), club: "Clube" })).toBe("Só para membros do clube da loja");
    expect(conditionLabel({ ...ordinary(), club: "Exemplo" })).toBe("Só para membros do Clube Exemplo");
  });

  it("spells out the other conditions, and says when there is none", () => {
    expect(conditionLabel({ ...ordinary(), coupon: "OFERTA10", min_quantity: 3, limit_per_customer: 6 })).toBe(
      "Exige cupom OFERTA10 · Levando 3 un. ou mais · Limite de 6 por cliente",
    );
    expect(conditionLabel(ordinary())).toBe("Sem condição especial");
  });
});
