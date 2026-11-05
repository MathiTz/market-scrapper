import { useQuery } from "@tanstack/react-query";
import type { Line } from "./list-storage";
import type { Account, Preferences, SavedList, Session } from "./account";

/** A failed account call, with the API's own message when it sent one. `status` is 0 when offline. */
export class AccountError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AccountError";
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, cache: "no-store", credentials: "same-origin" });
  } catch {
    throw new AccountError("Não foi possível conectar. Verifique sua conexão e tente de novo.", 0);
  }
  const body = (await response.json().catch(() => null)) as { error?: unknown } | null;
  if (!response.ok) {
    const message =
      typeof body?.error === "string" && body.error.trim() && body.error.length <= 200
        ? body.error
        : "Não foi possível concluir agora. Tente de novo.";
    throw new AccountError(message, response.status);
  }
  return body as T;
}

export type Credentials = { email: string; password: string; name?: string };
export type SignedIn = { user: Account; preferences: Preferences };

/** The account API (api/src/accounts.ts). The session rides in an HttpOnly cookie, so nothing is kept here. */
export const accountApi = {
  me: () => call<Session>("/api/auth/me"),
  register: (input: Credentials) =>
    call<SignedIn>("/api/auth/register", { method: "POST", body: JSON.stringify(input) }),
  login: (input: Credentials) =>
    call<SignedIn>("/api/auth/login", { method: "POST", body: JSON.stringify(input) }),
  logout: () => call<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  savePreferences: (preferences: Preferences) =>
    call<{ preferences: Preferences }>("/api/account/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    }),
  lists: () => call<{ lists: SavedList[] }>("/api/account/lists"),
  createList: (name: string, lines: Line[]) =>
    call<{ list: SavedList }>("/api/account/lists", {
      method: "POST",
      body: JSON.stringify({ name, lines }),
    }),
  updateList: (id: string, name: string, lines: Line[]) =>
    call<{ list: SavedList }>(`/api/account/lists/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ name, lines }),
    }),
  deleteList: (id: string) =>
    call<{ ok: boolean }>(`/api/account/lists/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export const ACCOUNT_QUERY_KEY = ["account"] as const;
export const SAVED_LISTS_QUERY_KEY = ["account", "lists"] as const;
export const savedListsKey = (userId: string) => [...SAVED_LISTS_QUERY_KEY, userId] as const;

/**
 * The signed-in shopper, or `{ user: null }`. A 401 is not an error: it is the normal signed-out state,
 * so the query never retries and never falls into an error panel.
 */
export function useAccount() {
  return useQuery({
    queryKey: ACCOUNT_QUERY_KEY,
    queryFn: accountApi.me,
    staleTime: 60_000,
    retry: 0,
  });
}
