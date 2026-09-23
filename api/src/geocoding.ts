// Address search for the UI's "Perto de você" filter, backed by Photon (OpenStreetMap data).
// The text a person types is sent to Photon, which the UI says before the search.

export type Place = { id: string; label: string; latitude: number; longitude: number };

const PHOTON_URL = "https://photon.komoot.io/api/";
const PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse";
const USER_AGENT = "mercado-em-dia/0.1 (price comparison for Fortaleza)";
const CENTER = { latitude: -3.7319, longitude: -38.5267 }; // results near it rank first
const BBOX = "-38.65,-3.95,-38.35,-3.65"; // west,south,east,north: Fortaleza and its surroundings
export const MIN_QUERY = 3;
export const MAX_QUERY = 120;
const LIMIT = 6;
const TIMEOUT_MS = 8000;
const CACHE_SECONDS = 24 * 60 * 60;

export class AddressSearchError extends Error {}

export const normalize = (query: unknown): string =>
  typeof query === "string" ? query.split(/\s+/).filter(Boolean).join(" ") : "";

type Feature = {
  geometry?: { type?: string; coordinates?: number[] };
  properties?: Record<string, string | number | undefined>;
};

function label(p: NonNullable<Feature["properties"]>): string {
  const street = p.street as string | undefined;
  const parts: string[] = [];
  if (p.name && p.name !== street) parts.push(String(p.name));
  if (street) parts.push(p.housenumber ? `${street}, ${p.housenumber}` : street);
  parts.push(String(p.district || p.locality || ""), String(p.city || ""));
  return [...new Set(parts.filter(Boolean))].join(" · ").slice(0, 240);
}

function place(feature: Feature): Place | null {
  const p = feature.properties ?? {};
  const coords = feature.geometry?.coordinates;
  if (feature.geometry?.type !== "Point" || !coords || coords.length < 2) return null;
  const text = label(p);
  if (!text || p.osm_id === undefined) return null;
  return { id: `${p.osm_type ?? ""}${p.osm_id}`, label: text, latitude: coords[1], longitude: coords[0] };
}

/** Places matching `query` in Fortaleza. Results are cached at Cloudflare's edge for a day. */
export async function searchAddresses(query: string, fetchImpl: typeof fetch = fetch): Promise<Place[]> {
  const params = new URLSearchParams({
    q: query,
    limit: String(LIMIT),
    lat: String(CENTER.latitude),
    lon: String(CENTER.longitude),
    bbox: BBOX,
  });
  let features: Feature[];
  try {
    const response = await fetchImpl(`${PHOTON_URL}?${params}`, {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      // Cloudflare-only options; ignored anywhere else.
      cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true },
    } as RequestInit);
    if (!response.ok) throw new Error(`Photon answered ${response.status}`);
    features = ((await response.json()) as { features?: Feature[] }).features ?? [];
  } catch (error) {
    throw new AddressSearchError(error instanceof Error ? error.message : "address service failed");
  }
  const seen = new Set<string>();
  const places: Place[] = [];
  for (const feature of features) {
    const found = place(feature);
    if (found && !seen.has(found.label)) {
      seen.add(found.label);
      places.push(found);
    }
  }
  return places;
}

/**
 * The address at a coordinate, or null when there is none. The coordinate is rounded to about 11 m
 * before it leaves for Photon: enough for a street address, and it lets identical lookups be cached.
 */
export async function reverseAddress(
  latitude: number,
  longitude: number,
  fetchImpl: typeof fetch = fetch,
): Promise<Place | null> {
  const params = new URLSearchParams({
    lat: latitude.toFixed(4),
    lon: longitude.toFixed(4),
    limit: "1",
  });
  let features: Feature[];
  try {
    const response = await fetchImpl(`${PHOTON_REVERSE_URL}?${params}`, {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true },
    } as RequestInit);
    if (!response.ok) throw new Error(`Photon answered ${response.status}`);
    features = ((await response.json()) as { features?: Feature[] }).features ?? [];
  } catch (error) {
    throw new AddressSearchError(error instanceof Error ? error.message : "address service failed");
  }
  for (const feature of features) {
    const found = place(feature);
    if (found) return found;
  }
  return null;
}
