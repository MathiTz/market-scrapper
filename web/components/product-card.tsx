import { useState, type CSSProperties } from "react";
import { Check, ChevronRight, Leaf, Navigation, Package, Plus, TriangleAlert } from "lucide-react";
import { money, rankOffers, type Product, type Offer } from "@/lib/domain";
import { productCardConditions } from "@/lib/product-presentation";
import { channelLabel, count, packLabel, unitPriceText, whenLabel } from "@/lib/format";
import { suspiciousSpread } from "@/lib/comparison";
import { offerLocation, distanceLabel, type LocationsByRetailer, type Nearby } from "@/lib/location";
import type { dailyDeals } from "@/lib/deals";
import { StoreLocation } from "./store-location";
import { OfferShare } from "./offer-share";
import { DealNote } from "./deal-note";
import { Tooltip } from "@/components/ui/tooltip";

/** Marks an image as loaded once decoded; a cached image fires no load event, so the mount checks `complete`. */
function useLoaded() {
  const [loaded, setLoaded] = useState(false);
  const ref = (element: HTMLImageElement | null) => {
    if (element?.complete && element.naturalWidth) setLoaded(true);
  };
  return { loaded, ref, onLoad: () => setLoaded(true) };
}

export function ProductPhoto({ product }: { product: Product }) {
  const [failedUrl, setFailedUrl] = useState("");
  const photo = useLoaded();
  return (
    <span className="product-photo">
      {product.image_url && product.image_url !== failedUrl ? (
        <img
          ref={photo.ref}
          src={product.image_url}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          data-loaded={photo.loaded}
          onLoad={photo.onLoad}
          onError={() => setFailedUrl(product.image_url!)}
        />
      ) : (
        <span className="product-photo-empty">
          <Package size={24} strokeWidth={1.3} aria-hidden="true" />
          <span>Sem foto</span>
        </span>
      )}
    </span>
  );
}

/** The big photo on a product's detail page: the same image the list cards show, or the "no image" box. */
export function ProductHero({ product }: { product: Product }) {
  const [failedUrl, setFailedUrl] = useState("");
  const photo = useLoaded();
  if (product.image_url && product.image_url !== failedUrl)
    return (
      <div className="product-hero">
        <img
          ref={photo.ref}
          src={product.image_url}
          alt={`Foto de ${product.name}`}
          decoding="async"
          referrerPolicy="no-referrer"
          data-loaded={photo.loaded}
          onLoad={photo.onLoad}
          onError={() => setFailedUrl(product.image_url!)}
        />
      </div>
    );
  return (
    <div className="product-placeholder">
      <Package size={30} strokeWidth={1.2} aria-hidden="true" />
      <span>Sem imagem</span>
    </div>
  );
}

/** Where the chain can be found, in the card's own words: see StoreContact for the same rule in the list. */
function locationText(o: Offer, nearby: Nearby | null, locationsByRetailer: LocationsByRetailer) {
  const branches = locationsByRetailer[o.retailer_id]?.length ?? 0;
  if (nearby) {
    const found = offerLocation(o, locationsByRetailer, nearby.point);
    if (!found) return "Unidades sem endereço conferido";
    return `${distanceLabel(found.distanceKm)} ${nearby.point.source === "device" ? "de você" : "da sua referência"} · unidade ${found.location.name}`;
  }
  if (!branches) return "Endereço das unidades não informado";
  return `${count(branches)} ${branches === 1 ? "unidade" : "unidades"} · defina seu local para ver a distância`;
}

export function ProductCard({
  p,
  offers,
  conditions,
  priceHidden,
  onOpen,
  onAdd,
  region,
  nearby,
  locationsByRetailer,
  deal,
  listQuantity = 0,
  style,
}: {
  p: Product;
  offers: Offer[];
  conditions: boolean;
  /** Why prices cannot be shown right now (offline, service failure), or undefined when they can. */
  priceHidden?: string;
  onOpen: (product: Product) => void;
  onAdd: (product: Product) => void;
  region: string;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  deal?: ReturnType<typeof dailyDeals>[number];
  /** How many of this product the shopping list already has. */
  listQuantity?: number;
  /** Layout variables from the parent (the rail's entrance order, `--i`). */
  style?: CSSProperties;
}) {
  const os = rankOffers(
    offers.filter((o) => o.product_id === p.id),
    conditions,
  );
  const o = priceHidden ? null : os[0];
  // Two chains 3x apart for "the same" product has so far meant a different unit of sale behind one name:
  // the card then shows no per-kg/L price (it would be computed from the wrong pack) and says to check.
  const suspect = suspiciousSpread(os);
  const unit = o && !suspect ? unitPriceText(p, o.price_cents!) : null;
  const another =
    os.find((offer) => offer.retailer_id !== o?.retailer_id) || os[1];
  const featured =
    deal?.best.id === o?.id && deal?.alternative.id === another?.id
      ? deal
      : undefined;
  const condition = o ? productCardConditions(o) : "Sem condição especial";
  const pack = packLabel(p);
  const priceText = o
    ? `${money(o.price_cents!)} no ${o.retailer_name}${condition !== "Sem condição especial" ? `, ${condition[0].toLowerCase()}${condition.slice(1)}` : ""}`
    : priceHidden || "sem preço atual";
  return (
    <article
      className={`product-card compact-product${featured ? " daily-deal" : ""}`}
      data-product-id={p.id}
      style={style}
    >
      <button
        className="product-open"
        aria-label={`${p.name}, ${pack}: ${priceText}. Ver detalhes e comparação`}
        onClick={() => onOpen(p)}
      >
        <ProductPhoto product={p} />
        <div className="product-summary">
          <h3>
            {p.name}
            {p.brand && !p.name.toLowerCase().includes(p.brand.toLowerCase()) ? ` ${p.brand}` : ""}
          </h3>
          <span className="product-pack">{pack}</span>
          {o ? (
            <div className="product-price-line">
              <strong className="price">{money(o.price_cents!)}</strong>
              {unit && <span className="muted unit-price">{unit}</span>}
              <DealNote offer={o} />
            </div>
          ) : (
            <span className="no-price">{priceHidden || "Sem preço atual"}</span>
          )}
        </div>
      </button>
      {o && condition !== "Sem condição especial" && (
        <span className="badge amber card-condition">{condition}</span>
      )}
      {o && (
        <div className="product-store">
          <strong>{o.retailer_name}</strong>
          <span className="product-seen">
            {channelLabel(o.channel)} · visto {whenLabel(o.price_observed_at)}
          </span>
          <span className="store-distance">
            <Navigation size={12} aria-hidden="true" />
            {locationText(o, nearby, locationsByRetailer)}
          </span>
        </div>
      )}
      {o && another && (
        <button
          className={`product-compare${suspect ? " compare-warning" : ""}`}
          onClick={() => onOpen(p)}
        >
          {suspect ? (
            <span className="compare-alert">
              <TriangleAlert size={13} aria-hidden="true" />
              Preços muito diferentes entre redes: confira a embalagem
            </span>
          ) : featured ? (
            <span className="daily-deal-label">
              <Leaf size={13} aria-hidden="true" />
              {money(featured.saving)} a menos que no {featured.alternative.retailer_name}
            </span>
          ) : (
            <span>
              {os.length} preços · também {money(another.price_cents!)} no {another.retailer_name}
            </span>
          )}
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      )}
      <div className="product-actions">
        {o && (
          <>
            <StoreLocation
              offer={o}
              productName={p.name}
              region={region}
              nearby={nearby}
              locations={locationsByRetailer[o.retailer_id] ?? []}
            />
            <OfferShare
              offer={o}
              productName={p.name}
              region={region}
              compact
            />
          </>
        )}
        <Tooltip label={listQuantity ? "Adicionar mais 1" : "Adicionar à lista"}>
          <button
            className={`add-button${listQuantity ? " in-list" : ""}`}
            aria-label={
              listQuantity
                ? `Adicionar mais 1 de ${p.name} (${listQuantity} na lista)`
                : `Adicionar ${p.name} à lista`
            }
            onClick={() => onAdd(p)}
          >
            {listQuantity ? (
              <>
                <Check size={16} aria-hidden="true" />
                <span className="in-list-count">{listQuantity}</span>
              </>
            ) : (
              <Plus size={18} aria-hidden="true" />
            )}
          </button>
        </Tooltip>
      </div>
    </article>
  );
}
