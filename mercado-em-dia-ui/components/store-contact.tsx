import { MapPin, Phone, Store } from "lucide-react";
import type { Offer } from "@/lib/domain";

/** ``address`` is the chain's real branch closest to wherever is relevant right now (see lib/location.ts's
 * offerLocation) - a chain has several, so it is resolved by the caller, not read off the offer itself. */
export function StoreContact({ offer, address }: { offer?: Offer | null; address?: string | null }) {
  const phone = offer?.store_phone;
  const demo = offer?.method === "demo";
  return (
    <div className="store-contact">
      <p>
        <Store size={16} aria-hidden="true" />
        <strong>{offer?.context_label || "Local ainda não definido"}</strong>
      </p>
      <p>
        <MapPin size={16} aria-hidden="true" />
        <span>{address || "Endereço não informado"}</span>
      </p>
      <p>
        <Phone size={16} aria-hidden="true" />
        {phone ? (
          demo ? (
            <span>{phone} · Telefone fictício</span>
          ) : (
            <a href={`tel:${phone.replace(/[^+\d]/g, "")}`}>{phone}</a>
          )
        ) : (
          <span>Telefone não informado</span>
        )}
      </p>
    </div>
  );
}
