import { describe, expect, it } from "vitest";
import { DEFAULT_LIMIT, limitOf, MAX_LIMIT, wordsOf } from "./search";

describe("wordsOf", () => {
  it("ignores accents, case and punctuation", () => {
    expect(wordsOf("  Feijão-Preto  1KG ")).toEqual(["feijao", "preto", "1kg"]);
  });
  it("is empty for a query too short or too long", () => {
    expect(wordsOf("a")).toEqual([]);
    expect(wordsOf("x".repeat(61))).toEqual([]);
    expect(wordsOf("   ")).toEqual([]);
  });
  it("keeps only letters and digits, so a word is safe in a pattern", () => {
    expect(wordsOf("arroz (.*) [a-z]+ \\d")).toEqual(["arroz", "a", "z", "d"]);
  });
  it("reads at most six words", () => {
    expect(wordsOf("a b c d e f g h")).toHaveLength(6);
  });
});

describe("limitOf", () => {
  it("defaults, and caps what can be asked", () => {
    expect(limitOf(undefined)).toBe(DEFAULT_LIMIT);
    expect(limitOf("abc")).toBe(DEFAULT_LIMIT);
    expect(limitOf("0")).toBe(DEFAULT_LIMIT);
    expect(limitOf("-3")).toBe(DEFAULT_LIMIT);
    expect(limitOf("12")).toBe(12);
    expect(limitOf("100000")).toBe(MAX_LIMIT);
  });
});
