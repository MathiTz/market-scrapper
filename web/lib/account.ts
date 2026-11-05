import type { Line } from "./list-storage";
import type { Nearby } from "./location";

/** One shopper, as the API returns it (api/src/accounts.ts). */
export type Account = {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
};

/** The reference "Perto de você" compares prices from, saved with the account. */
export type PreferredLocation = {
  label: string;
  latitude: number;
  longitude: number;
  radius_km: number;
};

export type Preferences = {
  region: string;
  location: PreferredLocation | null;
};

/** GET /api/auth/me. `google` says whether this deployment can sign in with Google at all. */
export type Session = {
  user: Account | null;
  preferences: Preferences | null;
  google: boolean;
};

export type SavedList = {
  id: string;
  name: string;
  lines: Line[];
  created_at: string;
  updated_at: string;
};

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 200;
export const MAX_LIST_NAME = 80;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Why the e-mail cannot be used, or null. Mirrors the API so the form can answer before a round trip. */
export function emailProblem(email: string): string | null {
  const value = email.trim();
  if (!value) return "Informe um e-mail.";
  if (value.length > 254) return "O e-mail pode ter no máximo 254 caracteres.";
  if (!EMAIL.test(value)) return "Digite um e-mail válido, como nome@exemplo.com.";
  return null;
}

/** Why the password cannot be used, or null. */
export function passwordProblem(password: string): string | null {
  if (password.length < MIN_PASSWORD) return `A senha precisa ter pelo menos ${MIN_PASSWORD} caracteres.`;
  if (password.length > MAX_PASSWORD) return `A senha pode ter no máximo ${MAX_PASSWORD} caracteres.`;
  return null;
}

export function listNameProblem(name: string): string | null {
  const value = name.trim();
  if (!value) return "Dê um nome à lista.";
  if (value.length > MAX_LIST_NAME) return `O nome pode ter no máximo ${MAX_LIST_NAME} caracteres.`;
  return null;
}

/** A name for the "save this list" box, dated so two lists from the same week are told apart. */
export function defaultListName(date = new Date()): string {
  const day = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(date);
  return `Mercado de ${day}`;
}

/** What to call the person: the first name they gave, else the part of the e-mail before the @. */
export function displayName(user: Account): string {
  const first = user.name?.trim().split(/\s+/)[0];
  return first || user.email.split("@")[0];
}

/** The account's saved place as the "Perto de você" filter expects it, or null when none is set. */
export function nearbyFromPreferences(preferences: Preferences | null | undefined): Nearby | null {
  const location = preferences?.location;
  if (!location) return null;
  return {
    point: {
      label: location.label,
      latitude: location.latitude,
      longitude: location.longitude,
      source: "manual",
    },
    radiusKm: location.radius_km,
  };
}

/** The filter's current value as preferences, for the account page to save. */
export function preferencesFromNearby(
  nearby: Nearby | null,
  region = "Fortaleza",
): Preferences {
  return {
    region,
    location: nearby
      ? {
          label: nearby.point.label,
          latitude: nearby.point.latitude,
          longitude: nearby.point.longitude,
          radius_km: nearby.radiusKm,
        }
      : null,
  };
}

/** A saved date in the account page's "salva em" line. */
export function accountDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "data desconhecida";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

/** `n itens` with the right singular, for the saved-list rows. */
export function itemCount(count: number): string {
  return `${count} ${count === 1 ? "item" : "itens"}`;
}

/** The lines to send to the API: only the fields it stores, in the shape it validates. */
export function savedLines(lines: Line[]): Line[] {
  return lines.map((line) => ({
    product_id: line.product_id,
    name: line.name,
    quantity: line.quantity,
    checked: line.checked,
  }));
}
