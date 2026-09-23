import { basket, type Offer } from "@/lib/domain";
import { nearestLocation, type LocationsByRetailer, type Nearby } from "@/lib/location";

export type StoreEstimate = ReturnType<typeof basket>[number] & {
  label: string;
  retailerName: string;
  /** Straight-line distance to the chain's nearest real branch from the chosen reference, when there is one. */
  distanceKm: number | null;
  /** The lowest total among the stores that cover the whole list. */
  cheapest: boolean;
  /** The closest store to the reference among those with a price for the list. */
  nearest: boolean;
};

/**
 * What the list would cost in each store, with the items behind each total. Only a store that covers
 * every item can be the cheapest (a partial total is lower just because it is missing things), and
 * the closest one is only known once a reference location is set.
 */
export function storeEstimates(
  lines: { product_id: string; quantity: number }[],
  offers: Offer[],
  nearby: Nearby | null,
  byRetailer: LocationsByRetailer,
): StoreEstimate[] {
  const firstOffer = new Map<string, Offer>();
  for (const o of offers) if (!firstOffer.has(o.context_id)) firstOffer.set(o.context_id, o);
  const stores = basket(lines, offers)
    .filter((t) => t.covered > 0)
    .map((t) => {
      const o = firstOffer.get(t.context_id)!;
      return {
        ...t,
        label: o.context_label,
        retailerName: o.retailer_name,
        distanceKm: nearby ? (nearestLocation(byRetailer[o.retailer_id], nearby.point)?.distanceKm ?? null) : null,
      };
    });
  const lowest = (list: typeof stores, by: (s: (typeof stores)[number]) => number) =>
    list.length ? list.reduce((a, b) => (by(b) < by(a) ? b : a)).context_id : null;
  const cheapest = lowest(stores.filter((s) => s.complete), (s) => s.total);
  const nearest = lowest(stores.filter((s) => s.distanceKm !== null), (s) => s.distanceKm!);
  return stores.map((s) => ({
    ...s,
    cheapest: s.context_id === cheapest,
    nearest: s.context_id === nearest,
  }));
}
