import { ArrowUpRight, Store } from "lucide-react";
import { conditionLabel, isConditional, localTime, money, type Offer, type Product } from "@/lib/domain";
import { channelLabel, unitPriceText, whenLabel } from "@/lib/format";
import { stockNote } from "@/lib/stock";
import { distanceLabel, offerLocation, type LocationsByRetailer, type Nearby } from "@/lib/location";
import { DealNote } from "./deal-note";
import { OfferShare } from "./offer-share";
import { StoreLocation } from "./store-location";

const methods: Record<Offer["method"], string> = {
  manual: "Registro manual identificado",
  automatic: "Coleta automática",
  demo: "Dado fictício",
};

/** One chain's price in a product's comparison: price and its conditions, where and when it was seen. */
export function OfferRow({
  offer: o,
  product,
  note,
  shared,
  demo,
  region,
  nearby,
  locationsByRetailer,
  hideUnitPrice,
}: {
  offer: Offer;
  product: Product;
  /** The lowest-price note for this row, if it has one (see lib/comparison.ts's lowestPriceLabel). */
  note: string | null;
  shared: boolean;
  demo: boolean;
  region: string;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  /** True when the comparison's prices are too far apart for a per-kg/L figure to be trusted. */
  hideUnitPrice: boolean;
}) {
  const found = nearby ? offerLocation(o, locationsByRetailer, nearby.point) : null;
  const unit = hideUnitPrice ? null : unitPriceText(product, o.price_cents!);
  const conditional = isConditional(o.conditions);
  const city = o.context_label.split(" · ").slice(1).join(" · ");
  const stock = stockNote(o);
  return (
    <article className={`offer-row${shared ? " shared-offer" : ""}`} id={`offer-${o.id}`}>
      <div className="store-mark" aria-hidden="true">
        <Store size={23} />
      </div>
      <div className="offer-details">
        {shared && <span className="badge green">Oferta compartilhada</span>}
        {note && (
          <span className="offer-note">
            {note}
            {conditional ? " (com condição)" : ""}
          </span>
        )}
        <h3>{o.retailer_name}</h3>
        <p>
          {channelLabel(o.channel)}
          {city && ` · ${city}`}
          {found && ` · unidade mais próxima ${distanceLabel(found.distanceKm)}`}
        </p>
        <span className={`badge ${conditional ? "amber" : "green"}`}>{conditionLabel(o.conditions)}</span>
        <p className="small">
          {o.channel === "flyer" ? "Preço anunciado no encarte" : "Preço visto no site"}{" "}
          {whenLabel(o.price_observed_at)}
          {o.valid_until && ` · válido até ${localTime(o.valid_until)}`}
        </p>
        <p className="small">
          {o.availability === "available"
            ? `Disponível no site na última consulta${stock ? ` · ${stock}` : ""}`
            : "Estoque não informado pela fonte"}{" "}
          · {methods[o.method]}
        </p>
        {o.collection_error && (
          <p className="small warning">Última coleta falhou; a observação não foi renovada.</p>
        )}
      </div>
      <div className="offer-value">
        <div className="offer-price">
          <strong>{money(o.price_cents!)}</strong>
          <DealNote offer={o} />
          {unit && <span>{unit}</span>}
        </div>
        <div className="offer-actions">
          {demo ? (
            <span className="small">Origem: exemplo fictício</span>
          ) : (
            <a href={o.source_url} target="_blank" rel="noreferrer">
              Ver no site da loja <ArrowUpRight size={16} aria-hidden="true" />
              <span className="sr-only"> (abre em nova aba)</span>
            </a>
          )}
          <OfferShare offer={o} productName={product.name} region={region} />
          <StoreLocation
            offer={o}
            productName={product.name}
            region={region}
            nearby={nearby}
            locations={locationsByRetailer[o.retailer_id] ?? []}
          />
        </div>
      </div>
    </article>
  );
}
