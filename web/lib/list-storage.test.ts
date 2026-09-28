import { describe, expect, it } from "vitest";
import { copyKey, readList, storageMessage, writeList } from "./list-storage";

function memory(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => void data.set(k, v),
  };
}

describe("readList", () => {
  it("reads a saved list", () => {
    const s = memory({ list: JSON.stringify([{ product_id: "324", name: "Lasanha", quantity: 2 }]) });
    expect(readList(s, "list")).toEqual({ lines: [{ product_id: "324", name: "Lasanha", quantity: 2 }], issue: null });
  });

  it("starts empty when nothing was saved", () => {
    expect(readList(memory(), "list")).toEqual({ lines: [], issue: null });
  });

  it("keeps a copy of an unreadable list instead of losing it", () => {
    const s = memory({ list: "{corrompido" });
    const result = readList(s, "list");
    expect(result).toEqual({ lines: [], issue: "unreadable" });
    expect(s.data.get(copyKey("list", "{corrompido"))).toBe("{corrompido");
    expect(s.data.get("list")).toBe("{corrompido"); // untouched until the next save
    readList(s, "list"); // read again (React does, in development): still one copy
    expect([...s.data.keys()].filter((k) => k.startsWith("list-copia-"))).toHaveLength(1);
  });

  it("keeps the valid lines, and a copy of the original, when some are invalid", () => {
    const raw = JSON.stringify([{ product_id: "1", name: "A", quantity: 1 }, { product_id: "", quantity: 0 }]);
    const s = memory({ list: raw });
    expect(readList(s, "list")).toEqual({ lines: [{ product_id: "1", name: "A", quantity: 1 }], issue: "partial" });
    expect(s.data.get(copyKey("list", raw))).toBe(raw);
  });

  it("reports storage the browser refuses", () => {
    const refusing = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("SecurityError");
      },
    };
    expect(readList(refusing, "list")).toEqual({ lines: [], issue: "blocked" });
    expect(readList(null, "list")).toEqual({ lines: [], issue: "blocked" });
    expect(writeList(refusing, "list", [])).toBe(false);
  });
});

describe("storageMessage", () => {
  it("explains every issue and nothing when there is none", () => {
    for (const issue of ["blocked", "unreadable", "partial", "save-failed"] as const) expect(storageMessage(issue)).toBeTruthy();
    expect(storageMessage(null)).toBeNull();
  });
});
