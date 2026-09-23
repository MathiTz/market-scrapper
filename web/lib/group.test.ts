import { describe, expect, it } from "vitest";
import type { Product } from "./domain";
import { groupBySize, sizelessName } from "./group";

const product = (id: string, name: string) => ({ id, name }) as unknown as Product;

describe("sizelessName", () => {
  it("removes a trailing size", () => {
    expect(sizelessName("Alho Picado Garlic Foods 200g")).toBe("Alho Picado Garlic Foods");
    expect(sizelessName("Água Mineral Crystal Sem Gas 1,5l")).toBe("Água Mineral Crystal Sem Gas");
  });

  it("removes only the size token, not a flavour that comes after it in the name", () => {
    // Real case: these three are the same 600g lasagne in three different flavours, not a size range -
    // an earlier version that stripped from the size to the end of the string merged them by mistake.
    expect(sizelessName("Lasanha Perdigão 600g Bolonhesa")).toBe("Lasanha Perdigão Bolonhesa");
    expect(sizelessName("Lasanha Perdigão 600g Calabresa")).toBe("Lasanha Perdigão Calabresa");
  });

  it("removes a size-shaped nutrition claim before the real size too, keeping the flavour distinct", () => {
    // Real case: "15g" here is "15g of protein", not the pack size (250ml, at the very end) - both are
    // size-shaped tokens, so both are removed, and the flavour between them still tells the products apart.
    expect(sizelessName("Bebida Lactea 3 Corações Cappuccino 15g De Proteina Baunilha 250ml")).toBe(
      "Bebida Lactea 3 Corações Cappuccino De Proteina Baunilha",
    );
    expect(sizelessName("Bebida Lactea 3 Corações Cappuccino 15g De Proteina Chocolate 250ml")).toBe(
      "Bebida Lactea 3 Corações Cappuccino De Proteina Chocolate",
    );
  });

  it("leaves a name with no size-shaped token alone", () => {
    expect(sizelessName("Arroz")).toBe("Arroz");
  });

  it("never returns an empty string, even for a name that is only a size", () => {
    expect(sizelessName("500g")).toBe("500g");
  });
});

describe("groupBySize", () => {
  const garlic1kg = product("g1", "Alho Picado Garlic Foods 1kg");
  const garlic200g = product("g2", "Alho Picado Garlic Foods 200g");
  const garlic400g = product("g3", "Alho Picado Garlic Foods 400g");
  const rice = product("r1", "Arroz Branco Tipo 1 1kg");
  const lasagneBolonhesa = product("l1", "Lasanha Perdigão 600g Bolonhesa");
  const lasagneCalabresa = product("l2", "Lasanha Perdigão 600g Calabresa");

  it("collapses same-line size variants into one group, in members' catalogue order", () => {
    const result = groupBySize([garlic200g, rice, garlic1kg, garlic400g]);
    expect(result).toHaveLength(2); // the group, plus the lone rice
    const [group, loneRice] = result;
    expect(loneRice).toBe(rice); // untouched, not wrapped
    expect("members" in group!).toBe(true);
    if ("members" in group!) {
      expect(group.name).toBe("Alho Picado Garlic Foods");
      expect(group.members).toEqual([garlic200g, garlic1kg, garlic400g]); // input order, not re-sorted by size
    }
  });

  it("places the group at the position of the first variant encountered, so a sort order is preserved", () => {
    const result = groupBySize([rice, garlic1kg, garlic200g]);
    expect(result[0]).toBe(rice);
    expect("members" in result[1]!).toBe(true); // the group takes garlic1kg's slot, not the end of the list
  });

  it("a lone product (no other size present) is not wrapped in a group", () => {
    const result = groupBySize([garlic1kg, rice]);
    expect(result).toEqual([garlic1kg, rice]);
  });

  it("does not group same-size different flavours as if they were a size range", () => {
    const result = groupBySize([lasagneBolonhesa, lasagneCalabresa]);
    expect(result).toEqual([lasagneBolonhesa, lasagneCalabresa]); // two lone products, not one group
  });

  it("an empty list stays empty", () => {
    expect(groupBySize([])).toEqual([]);
  });
});
