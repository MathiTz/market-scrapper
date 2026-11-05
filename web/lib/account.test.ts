import { describe, expect, it } from "vitest";
import {
  accountDate,
  browsingRegion,
  defaultListName,
  displayName,
  emailProblem,
  itemCount,
  listNameProblem,
  nearbyFromPreferences,
  passwordProblem,
  preferencesFromNearby,
  savedLines,
  type Account,
  type Preferences,
} from "./account";
import { BRAND } from "./domain";

describe("account form validation", () => {
  it.each([
    ["", "Informe um e-mail."],
    ["  ", "Informe um e-mail."],
    ["sem-arroba", "Digite um e-mail válido, como nome@exemplo.com."],
    ["a@b", "Digite um e-mail válido, como nome@exemplo.com."],
    ["a@b.c", "Digite um e-mail válido, como nome@exemplo.com."],
    [`${"x".repeat(250)}@example.com`, "O e-mail pode ter no máximo 254 caracteres."],
  ])("refuses the e-mail %j", (email, message) => {
    expect(emailProblem(email)).toBe(message);
  });

  it.each(["ana@example.com", " ana@example.com ", "nome.sobrenome+tag@escola.com.br"])(
    "accepts the e-mail %j",
    (email) => {
      expect(emailProblem(email)).toBeNull();
    },
  );

  it.each([
    ["", "A senha precisa ter pelo menos 8 caracteres."],
    ["1234567", "A senha precisa ter pelo menos 8 caracteres."],
    ["🛒".repeat(4), "A senha precisa ter pelo menos 8 caracteres."],
    ["1".repeat(201), "A senha pode ter no máximo 200 caracteres."],
    ["🛒".repeat(201), "A senha pode ter no máximo 200 caracteres."],
  ])("refuses the password %j", (password, message) => {
    expect(passwordProblem(password)).toBe(message);
  });

  it("accepts eight characters, accents and spaces", () => {
    expect(passwordProblem("segredo123")).toBeNull();
    expect(passwordProblem("senha com espaço")).toBeNull();
    expect(passwordProblem("🛒".repeat(8))).toBeNull();
  });

  it("asks for a list name that fits", () => {
    expect(listNameProblem("")).toBe("Dê um nome à lista.");
    expect(listNameProblem("   ")).toBe("Dê um nome à lista.");
    expect(listNameProblem("x".repeat(81))).toBe("O nome pode ter no máximo 80 caracteres.");
    expect(listNameProblem("Mercado da semana")).toBeNull();
  });
});

describe("account presentation", () => {
  const account: Account = {
    id: "u1",
    email: "ana.silva@example.com",
    name: null,
    created_at: "2026-11-05T12:00:00.000Z",
  };

  it("uses the given first name, else the e-mail's local part", () => {
    expect(displayName(account)).toBe("ana.silva");
    expect(displayName({ ...account, name: "Ana Maria Silva" })).toBe("Ana");
    expect(displayName({ ...account, name: "   " })).toBe("ana.silva");
  });

  it("dates the default list name", () => {
    expect(defaultListName(new Date(2026, 10, 5))).toBe("Mercado de 05/11");
  });

  it("counts items in the singular and the plural", () => {
    expect(itemCount(1)).toBe("1 item");
    expect(itemCount(0)).toBe("0 itens");
    expect(itemCount(12)).toBe("12 itens");
  });

  it("formats a saved date, and says so when the date is unusable", () => {
    expect(accountDate("2026-11-05T12:00:00.000Z")).toMatch(/05\/11\/2026/);
    expect(accountDate("not a date")).toBe("data desconhecida");
  });

  it("keeps only the fields the account list stores", () => {
    const lines = savedLines([
      { product_id: "arroz", name: "Arroz 5 kg", quantity: 2, checked: true },
      { product_id: "feijao", name: "Feijão", quantity: 1, checked: false },
    ]);
    expect(lines).toEqual([
      { product_id: "arroz", name: "Arroz 5 kg", quantity: 2, checked: true },
      { product_id: "feijao", name: "Feijão", quantity: 1, checked: false },
    ]);
  });
});

describe("browsingRegion", () => {
  it("reads the stored region when available", () => {
    expect(browsingRegion({ getItem: () => "Caucaia" })).toBe("Caucaia");
  });

  it("falls back to BRAND.city when storage is absent or throws", () => {
    expect(browsingRegion(null)).toBe(BRAND.city);
    expect(
      browsingRegion({
        getItem: () => {
          throw new Error("storage blocked");
        },
      }),
    ).toBe(BRAND.city);
  });
});

describe("preferred location", () => {
  const preferences: Preferences = {
    region: "Fortaleza",
    location: { label: "Casa · Rua A, 10 · Meireles", latitude: -3.72, longitude: -38.5, radius_km: 5 },
  };

  it("turns the saved place into the nearby filter's value", () => {
    expect(nearbyFromPreferences(preferences)).toEqual({
      point: {
        label: "Casa · Rua A, 10 · Meireles",
        latitude: -3.72,
        longitude: -38.5,
        source: "manual",
      },
      radiusKm: 5,
    });
  });

  it("is null without a saved place or without an account", () => {
    expect(nearbyFromPreferences({ region: "Fortaleza", location: null })).toBeNull();
    expect(nearbyFromPreferences(null)).toBeNull();
    expect(nearbyFromPreferences(undefined)).toBeNull();
  });

  it("returns null for a region mismatch and still returns the Nearby for the matching region", () => {
    const caucaiaPreferences: Preferences = { ...preferences, region: "Caucaia" };
    // region mismatch via preferences.region
    expect(nearbyFromPreferences(caucaiaPreferences, "Fortaleza")).toBeNull();
    // region mismatch via the second argument
    expect(nearbyFromPreferences(preferences, "Caucaia")).toBeNull();
    // matching region still returns the Nearby
    expect(nearbyFromPreferences(caucaiaPreferences, "Caucaia")).toEqual({
      point: {
        label: "Casa · Rua A, 10 · Meireles",
        latitude: -3.72,
        longitude: -38.5,
        source: "manual",
      },
      radiusKm: 5,
    });
  });

  it("round-trips through preferencesFromNearby", () => {
    const nearby = nearbyFromPreferences(preferences);
    expect(preferencesFromNearby(nearby)).toEqual(preferences);
    expect(preferencesFromNearby(null)).toEqual({ region: "Fortaleza", location: null });
    expect(preferencesFromNearby(nearby, "Caucaia").region).toBe("Caucaia");
  });
});
