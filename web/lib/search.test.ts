import { describe, expect, it } from "vitest";
import { buildIndex, filterIndexed, matchesQuery, searchIndexed, searchProducts } from "./search";

describe("matchesQuery", () => {
  const perola = "Abacaxi Pérola Unidade";

  it("matches each typed word as the start of some word, so partial words work", () => {
    expect(matchesQuery(perola, "abacaxi u")).toBe(true); // used to find nothing
    expect(matchesQuery(perola, "abacaxi p")).toBe(true);
    expect(matchesQuery(perola, "aba")).toBe(true);
    expect(matchesQuery(perola, "abacaxi pre")).toBe(false);
  });

  it("ignores accents, case and extra spaces", () => {
    expect(matchesQuery("ABACAXI PÉROLA UNIDADE", "  abacaxi   perola ")).toBe(true);
    expect(matchesQuery("Feijão Preto", "feijao")).toBe(true);
    expect(matchesQuery("Feijao", "FEIJÃO")).toBe(true);
  });

  it("does not care about word order", () => {
    expect(matchesQuery(perola, "unidade abacaxi")).toBe(true);
  });

  it("only matches at the start of words, not inside them", () => {
    expect(matchesQuery("Banana Prata", "nana")).toBe(false);
    expect(matchesQuery("Banana Prata", "prat")).toBe(true);
  });

  it("matches sizes with or without a space", () => {
    expect(matchesQuery("Arroz Tio João 5 kg", "5kg")).toBe(true);
    expect(matchesQuery("Leite 500 ml", "500ml")).toBe(true);
    expect(matchesQuery("Leite 1l", "500ml")).toBe(false);
  });

  it("matches everything when nothing is typed, and nothing for an unrelated word", () => {
    expect(matchesQuery(perola, "")).toBe(true);
    expect(matchesQuery(perola, "   ")).toBe(true);
    expect(matchesQuery(perola, "laranja")).toBe(false);
  });
});

describe("searchProducts", () => {
  const products = [
    { name: "Suco de Banana 1l" },
    { name: "Banana Prata Kg" },
    { name: "Banana Nanica Bandeja 1kg" },
    { name: "Banana Ouro" },
    { name: "Bolo de Banana" },
    { name: "Arroz" },
  ];

  it("lists the variants of what was typed, best first", () => {
    const names = searchProducts(products, "banana").map((p) => p.name);
    expect(names.slice(0, 3)).toEqual(["Banana Ouro", "Banana Prata Kg", "Banana Nanica Bandeja 1kg"]);
    expect(names).not.toContain("Arroz");
    expect(names.at(-1)).toMatch(/Suco|Bolo/); // names that only contain the word come after
  });

  it("narrows as more is typed", () => {
    expect(searchProducts(products, "banana pr").map((p) => p.name)).toEqual(["Banana Prata Kg"]);
  });

  it("respects the limit", () => {
    expect(searchProducts(products, "banana", 2)).toHaveLength(2);
  });
});

describe("buildIndex + searchIndexed/filterIndexed", () => {
  const products = [
    { name: "Suco de Banana 1l" },
    { name: "Banana Prata Kg" },
    { name: "Banana Nanica Bandeja 1kg" },
    { name: "Banana Ouro" },
    { name: "Bolo de Banana" },
    { name: "Arroz" },
  ];
  const index = buildIndex(products, (p) => p.name);

  it("searchIndexed matches searchProducts against the same list", () => {
    expect(searchIndexed(index, "banana").map((p) => p.name)).toEqual(
      searchProducts(products, "banana").map((p) => p.name),
    );
    expect(searchIndexed(index, "banana pr").map((p) => p.name)).toEqual(["Banana Prata Kg"]);
    expect(searchIndexed(index, "banana", 2)).toHaveLength(2);
  });

  it("the index can be reused for several different searches without rebuilding it", () => {
    expect(searchIndexed(index, "arroz").map((p) => p.name)).toEqual(["Arroz"]);
    expect(searchIndexed(index, "ouro").map((p) => p.name)).toEqual(["Banana Ouro"]);
    expect(searchIndexed(index, "banana pr").map((p) => p.name)).toEqual(["Banana Prata Kg"]);
  });

  it("filterIndexed keeps every match, in the original order, with no limit", () => {
    const names = filterIndexed(index, "banana").map((p) => p.name);
    expect(names).toEqual([
      "Suco de Banana 1l", "Banana Prata Kg", "Banana Nanica Bandeja 1kg", "Banana Ouro", "Bolo de Banana",
    ]); // the products array's own order, not "best match first"
  });

  it("filterIndexed returns everything when nothing is typed", () => {
    expect(filterIndexed(index, "")).toHaveLength(products.length);
  });

  it("filterIndexed returns nothing for an unrelated word", () => {
    expect(filterIndexed(index, "laranja")).toEqual([]);
  });

  it("an empty product list indexes and searches without error", () => {
    const empty = buildIndex<{ name: string }>([], (p) => p.name);
    expect(searchIndexed(empty, "banana")).toEqual([]);
    expect(filterIndexed(empty, "banana")).toEqual([]);
  });

  it("indexes text other than the item's own name (e.g. name + brand)", () => {
    const withBrand = [{ name: "Refrigerante", brand: "Cometa" }, { name: "Suco", brand: "Del Valle" }];
    const byNameAndBrand = buildIndex(withBrand, (p) => `${p.name} ${p.brand}`);
    expect(filterIndexed(byNameAndBrand, "cometa").map((p) => p.name)).toEqual(["Refrigerante"]);
  });
});
