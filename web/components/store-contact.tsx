import { MapPin, Phone } from "lucide-react";
import type { Offer } from "@/lib/domain";
import { count } from "@/lib/format";
import { distanceLabel, nearestLocation, type Nearby, type RetailerLocation } from "@/lib/location";

/**
 * Where the chain of an offer can be found, in one or two lines: the branch nearest to the person's own
 * reference once they set one, otherwise how many branches the chain has - never a branch picked for them.
 */
export function StoreContact({
  offer,
  nearby,
  locations,
}: {
  offer: Offer;
  nearby: Nearby | null;
  locations: RetailerLocation[];
}) {
  const found = nearby ? nearestLocation(locations, nearby.point) : null;
  const phone = offer.store_phone;
  const demo = offer.method === "demo";
  return (
    <div className="store-contact">
      <p>
        <MapPin size={16} aria-hidden="true" />
        {found ? (
          <span>
            Unidade mais próxima: {found.location.name} · {distanceLabel(found.distanceKm)} em linha reta
            <span className="store-contact-address">{found.location.address}</span>
          </span>
        ) : locations.length ? (
          <span>
            {count(locations.length)} {locations.length === 1 ? "unidade cadastrada" : "unidades cadastradas"} ·
            defina seu local para ver a mais próxima
          </span>
        ) : (
          <span>Endereço das unidades não informado pela fonte</span>
        )}
      </p>
      {phone && (
        <p>
          <Phone size={16} aria-hidden="true" />
          {demo ? (
            <span>{phone} · telefone fictício</span>
          ) : (
            <a href={`tel:${phone.replace(/[^+\d]/g, "")}`}>{phone}</a>
          )}
        </p>
      )}
    </div>
  );
}
