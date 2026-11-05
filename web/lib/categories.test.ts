import { describe, expect, it } from "vitest";
import type { Product } from "./domain";
import { departmentsOf, inDepartment } from "./categories";

const product = (id: string, department: string | null): Product =>
  ({ id, name: id, category_department: department }) as unknown as Product;

describe("departmentsOf", () => {
  it("lists the departments present, biggest first", () => {
    const list = [
      product("a", "Bebidas"),
      product("b", "Bebidas"),
      product("c", "Limpeza"),
      product("d", "Lanches e Doces"),
      product("e", "Lanches e Doces"),
      product("f", "Lanches e Doces"),
    ];
    expect(departmentsOf(list)).toEqual(["Lanches e Doces", "Bebidas", "Limpeza"]);
  });

  it("breaks ties by name so the row does not reshuffle between loads", () => {
    const list = [product("a", "Limpeza"), product("b", "Bebidas")];
    expect(departmentsOf(list)).toEqual(["Bebidas", "Limpeza"]);
  });

  it("leaves out the products the Cosmos tree has no node for", () => {
    // They keep their keyword category and are reachable through "Todas" and search - never a guessed chip.
    expect(departmentsOf([product("a", null), product("b", "Bebidas")])).toEqual(["Bebidas"]);
    expect(departmentsOf([product("a", null)])).toEqual([]);
  });

  it("is empty for a snapshot published without a warehouse", () => {
    expect(departmentsOf([])).toEqual([]);
  });
});

describe("inDepartment", () => {
  it("matches only the chosen department", () => {
    expect(inDepartment(product("a", "Bebidas"), "Bebidas")).toBe(true);
    expect(inDepartment(product("a", "Bebidas"), "Limpeza")).toBe(false);
    expect(inDepartment(product("a", null), "Bebidas")).toBe(false);
  });
});
