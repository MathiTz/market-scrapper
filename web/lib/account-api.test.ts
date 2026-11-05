import { describe, expect, it } from "vitest";
import { SAVED_LISTS_QUERY_KEY, savedListsKey } from "./account-api";

describe("savedListsKey", () => {
  it("builds a user-scoped query key with SAVED_LISTS_QUERY_KEY as prefix", () => {
    const key1 = savedListsKey("user-1");
    const key2 = savedListsKey("user-2");

    expect(key1).toEqual(["account", "lists", "user-1"]);
    expect(key2).toEqual(["account", "lists", "user-2"]);
    expect(key1).not.toEqual(key2);

    expect(key1.slice(0, SAVED_LISTS_QUERY_KEY.length)).toEqual(SAVED_LISTS_QUERY_KEY);
    expect(key2.slice(0, SAVED_LISTS_QUERY_KEY.length)).toEqual(SAVED_LISTS_QUERY_KEY);
  });
});
