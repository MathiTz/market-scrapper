import { validCoordinates } from "./location";

export type AddressResult = { id: string; label: string; latitude: number; longitude: number };

const TIMEOUT_MS = 15_000;

/**
 * POST /api/location: address suggestions for the typed text (Photon/OpenStreetMap behind the API).
 * Throws an Error whose message is fit for the screen; the caller decides where to show it.
 */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<AddressResult[]> {
  let response: Response;
  try {
    response = await fetch("/api/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      cache: "no-store",
      signal: signal ?? AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new Error("A busca de endereço demorou mais que o esperado. Tente novamente.");
  }
  const data = (await response.json().catch(() => null)) as {
    places?: unknown;
    error?: unknown;
  } | null;
  if (!response.ok)
    throw new Error(
      typeof data?.error === "string" && data.error.trim()
        ? data.error
        : "Não foi possível buscar o endereço agora.",
    );
  if (!Array.isArray(data?.places)) return [];
  return data.places.filter(
    (place: AddressResult) =>
      place &&
      typeof place.id === "string" &&
      typeof place.label === "string" &&
      validCoordinates(place),
  );
}

/** GET /api/location/reverse: the street address at a GPS position, or null when it cannot be found. */
export async function addressAt(latitude: number, longitude: number): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      lat: latitude.toFixed(4),
      lon: longitude.toFixed(4),
    });
    const response = await fetch("/api/location/reverse?" + params, {
      signal: AbortSignal.timeout(6000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    return typeof data?.place?.label === "string" ? data.place.label : null;
  } catch {
    return null;
  }
}
