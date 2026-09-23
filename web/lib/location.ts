import type { Offer } from "./domain";

export type Coordinates = { latitude: number; longitude: number };
export type LocationPoint = Coordinates & {
  label: string;
  source: "manual" | "device";
  accuracy?: number;
};
export type Nearby = { point: LocationPoint; radiusKm: number };
export const radii = [2, 5, 10, 20] as const;

// Central Fortaleza: the reference used to pick which branch to show before a person sets their own -
// the same point the address search (nearby-filter.tsx) and the server's geocoding are biased toward.
export const FORTALEZA_CENTER: Coordinates = { latitude: -3.7319, longitude: -38.5267 };

/** A chain's real, physical branch (see the snapshot's `retailer_locations`); a retailer usually has several. */
export type RetailerLocation = {
  id: string;
  retailer_id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
};

/** A snapshot's locations grouped by the retailer they belong to; build once per snapshot with {@link groupLocations}. */
export type LocationsByRetailer = Record<string, RetailerLocation[]>;

export function groupLocations(locations: RetailerLocation[]): LocationsByRetailer {
  const byRetailer: LocationsByRetailer = {};
  for (const location of locations) {
    (byRetailer[location.retailer_id] ??= []).push(location);
  }
  return byRetailer;
}

export function validCoordinates(p: Coordinates) {
  return (
    typeof p.latitude === "number" &&
    typeof p.longitude === "number" &&
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    Math.abs(p.latitude) <= 90 &&
    Math.abs(p.longitude) <= 180
  );
}
export function distanceKm(a: Coordinates, b: Coordinates): number | null {
  if (!validCoordinates(a) || !validCoordinates(b)) return null;
  const radians = (n: number) => (n * Math.PI) / 180;
  const h =
    Math.sin(radians(b.latitude - a.latitude) / 2) ** 2 +
    Math.cos(radians(a.latitude)) *
      Math.cos(radians(b.latitude)) *
      Math.sin(radians(b.longitude - a.longitude) / 2) ** 2;
  return (
    6371.0088 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)))
  );
}

/** Of a retailer's real branches, the one closest to `point`, with the distance there; null with no branches. */
export function nearestLocation(
  locations: RetailerLocation[] | undefined,
  point: Coordinates,
): { location: RetailerLocation; distanceKm: number } | null {
  let best: { location: RetailerLocation; distanceKm: number } | null = null;
  for (const location of locations || []) {
    const distance = distanceKm(point, location);
    if (distance !== null && (!best || distance < best.distanceKm)) {
      best = { location, distanceKm: distance };
    }
  }
  return best;
}

/** An offer's chain's nearest branch to `point`: what "how far is this offer" and "its address" both mean now
 * that a chain can have several real branches - see the note on `Store.address` in models/store.py. */
export function offerLocation(offer: Offer, byRetailer: LocationsByRetailer, point: Coordinates) {
  return nearestLocation(byRetailer[offer.retailer_id], point);
}

export function distanceLabel(km: number) {
  return `≈ ${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(km)} km`;
}
export function filterNearby(offers: Offer[], nearby: Nearby | null, byRetailer: LocationsByRetailer) {
  if (!nearby) return offers;
  return offers.filter((offer) => {
    const found = offerLocation(offer, byRetailer, nearby.point);
    return found !== null && found.distanceKm <= nearby.radiusKm;
  });
}
export function readNearby(value: string | null): Nearby | null {
  try {
    const n = JSON.parse(value || "null");
    if (
      !n ||
      !n.point ||
      !validCoordinates(n.point) ||
      !radii.some((r) => r === n.radiusKm) ||
      !["manual", "device"].includes(n.point.source) ||
      typeof n.point.label !== "string" ||
      !n.point.label.trim() ||
      n.point.label.length > 240 ||
      (n.point.accuracy !== undefined &&
        (!Number.isFinite(n.point.accuracy) ||
          n.point.accuracy < 0 ||
          n.point.accuracy > 2000))
    )
      return null;
    return {
      point: {
        latitude: n.point.latitude,
        longitude: n.point.longitude,
        label: n.point.label,
        source: n.point.source,
        ...(n.point.accuracy === undefined
          ? {}
          : { accuracy: n.point.accuracy }),
      },
      radiusKm: n.radiusKm,
    };
  } catch {
    return null;
  }
}
