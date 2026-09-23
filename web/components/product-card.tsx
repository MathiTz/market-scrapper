import { useState } from "react";
import { Plus, Package, ChevronRight, Leaf, Navigation } from "lucide-react";
import { money, rankOffers, unitPrice, type Product, type Offer } from "@/lib/domain";
import { productCardConditions } from "@/lib/product-presentation";
import { offerLocation, distanceLabel, FORTALEZA_CENTER, type LocationsByRetailer, type Nearby } from "@/lib/location";
import type { dailyDeals } from "@/lib/deals";
import { StoreLocation } from "./store-location";
import { OfferShare } from "./offer-share";
import { DealNote } from "./deal-note";

export function ProductPhoto({ product }: { product: Product }) {
  const [failedUrl, setFailedUrl] = useState("");
  return (
    <span className="product-photo">
      {product.image_url && product.image_url !== failedUrl ? (
        <img
          src={product.image_url}
          alt={`${product.name} ${product.brand}`}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(product.image_url!)}
        />
      ) : (
        <span className="product-photo-empty">
          <Package size={24} strokeWidth={1.3} />
          <span>Sem foto</span>
        </span>
      )}
    </span>
  );
}

export function ProductCard({
  p,
  offers,
  conditions,
  unavailable,
  onOpen,
  onAdd,
  region,
  nearby,
  locationsByRetailer,
  deal,
}: {
  p: Product;
  offers: Offer[];
  conditions: boolean;
  unavailable: boolean;
  onOpen: (product: Product) => void;
  onAdd: (product: Product) => void;
  region: string;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  deal?: ReturnType<typeof dailyDeals>[number];
}) {
  const os = rankOffers(
    offers.filter((o) => o.product_id === p.id),
    conditions,
  );
  const o = unavailable ? null : os[0];
  // The address always shows the chain's real branch nearest to wherever is relevant right now: the
  // person's own reference once they set one, central Fortaleza otherwise. The distance line itself only
  // appears once they have actually chosen a reference - showing "≈ 0 km from central Fortaleza" by
  // default would read as a location we know about you, not a generic starting point.
  const found = o ? offerLocation(o, locationsByRetailer, nearby?.point ?? FORTALEZA_CENTER) : null;
  const distance = nearby ? (found?.distanceKm ?? null) : null;
  // Shown next to the price whenever the pack isn't already exactly one kg/L/unit - "R$20,00 (200g)"
  // alone hides that a 1kg bag at R$90 is cheaper; the per-kg/L/unit figure makes packs comparable.
  const up = o ? unitPrice(p, o.price_cents!) : null;
  const another =
    os.find((offer) => offer.retailer_id !== o?.retailer_id) || os[1];
  const featured =
    deal?.best.id === o?.id && deal?.alternative.id === another?.id
      ? deal
      : undefined;
  const condition = o ? productCardConditions(o) : "Sem condição especial";
  return (
    <article
      className={`product-card compact-product${featured ? " daily-deal" : ""}`}
    >
      <button
        className="product-open"
        aria-label={[p.brand, p.name, p.variant, `${p.amount} ${p.unit}`].filter(Boolean).join(" · ")}
        onClick={() => onOpen(p)}
      >
        <ProductPhoto product={p} />
        <div className="product-summary">
          <h3>
            {p.name} {p.brand}
          </h3>
          <span className="product-pack">
            {p.variant && `${p.variant} · `}{p.pack_count > 1 ? `${p.pack_count} × ` : ""}
            {p.amount} {p.unit}
          </span>
          {o ? (
            <div className="product-price-line">
              <strong className="price">{money(o.price_cents!)}</strong>
              {up && up.value !== o.price_cents && (
                <span className="muted unit-price">
                  {money(up.value)}/{up.unit}
                </span>
              )}
              <DealNote offer={o} />
            </div>
          ) : (
            <span className="no-price">Sem preço atual</span>
          )}
        </div>
      </button>
      {o && (
        <div className="product-store">
          <strong>{o.retailer_name}</strong>
          <span className="product-address">
            {found?.location.address || "Endereço completo não informado"}
          </span>
          <span
            className="store-distance"
            title="Distância aproximada em linha reta, sem considerar o trajeto."
          >
            <Navigation size={12} aria-hidden="true" />
            {distance !== null
              ? `${distanceLabel(distance)} ${nearby?.point.source === "device" ? "de você" : "da sua referência"}`
              : nearby
                ? "Distância não disponível"
                : "Defina seu local para ver a distância"}
          </span>
          {condition !== "Sem condição especial" && (
            <span className="badge amber">{condition}</span>
          )}
        </div>
      )}
      {o && another && (
        <button
          className="product-compare"
          onClick={() => onOpen(p)}
          aria-label={`Comparar ${os.length} preços de ${p.name}`}
        >
          {featured ? (
            <span
              className="daily-deal-label"
              title={`Diferença para ${featured.alternative.retailer_name}, para o mesmo produto e embalagem.`}
            >
              <Leaf size={13} />
              {money(featured.saving)} a menos
            </span>
          ) : (
            <span>{os.length} preços</span>
          )}
          <span title={another.retailer_name}>
            Também {money(another.price_cents!)} <ChevronRight size={14} />
          </span>
        </button>
      )}
      <div className="product-actions">
        {o && (
          <>
            <StoreLocation offer={o} productName={p.name} region={region} address={found?.location.address ?? null} />
            <OfferShare
              offer={o}
              productName={p.name}
              region={region}
              compact
            />
          </>
        )}
        <button
          className="add-button"
          aria-label={`Adicionar ${p.name}`}
          onClick={() => onAdd(p)}
        >
          <Plus size={18} />
        </button>
      </div>
      {o?.channel === "catalog" && (
        <p className="price-disclaimer">
          Preço online. Na loja, o valor pode variar.
        </p>
      )}
    </article>
  );
}
