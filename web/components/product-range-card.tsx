import { useEffect, useId, useRef, useState } from "react";
import { ChevronRight, Plus, X } from "lucide-react";
import { money, rankOffers, unitPrice, type Offer, type Product } from "@/lib/domain";
import type { ProductGroup } from "@/lib/group";
import { offerLocation, distanceLabel, FORTALEZA_CENTER, type LocationsByRetailer, type Nearby } from "@/lib/location";
import { ProductPhoto } from "./product-card";

/** A group member's own best current offer, resolved once and shared by the card and its modal row. */
function bestOfferOf(product: Product, offersByProduct: Map<string, Offer[]>, conditions: boolean) {
  return rankOffers(offersByProduct.get(product.id) ?? [], conditions)[0] ?? null;
}

function SizeRow({
  product,
  offer,
  nearby,
  locationsByRetailer,
  onOpen,
  onAdd,
}: {
  product: Product;
  offer: Offer | null;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  onOpen: () => void;
  onAdd: () => void;
}) {
  const found = offer ? offerLocation(offer, locationsByRetailer, nearby?.point ?? FORTALEZA_CENTER) : null;
  const distance = nearby && found ? distanceLabel(found.distanceKm) : null;
  const up = offer ? unitPrice(product, offer.price_cents!) : null;
  return (
    <li className="size-row">
      <button type="button" className="size-row-open" onClick={onOpen}>
        <span className="size-row-pack">
          {product.variant && `${product.variant} · `}
          {product.pack_count > 1 ? `${product.pack_count} × ` : ""}
          {product.amount} {product.unit}
        </span>
        {offer ? (
          <>
            <strong>{money(offer.price_cents!)}</strong>
            {up && up.value !== offer.price_cents && (
              <span className="muted unit-price">
                {money(up.value)}/{up.unit}
              </span>
            )}
            <span className="muted">
              {offer.retailer_name}
              {distance && ` · ${distance}`}
            </span>
          </>
        ) : (
          <span className="no-price">Sem preço atual</span>
        )}
      </button>
      {offer && (
        <button type="button" className="size-row-add" aria-label={`Adicionar ${product.name} à lista`} onClick={onAdd}>
          <Plus size={16} />
        </button>
      )}
    </li>
  );
}

export function ProductRangeCard({
  group,
  offersByProduct,
  conditions,
  nearby,
  locationsByRetailer,
  onOpen,
  onAdd,
}: {
  group: ProductGroup;
  offersByProduct: Map<string, Offer[]>;
  conditions: boolean;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  onOpen: (product: Product) => void;
  onAdd: (product: Product) => void;
}) {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  const priced = group.members
    .map((product) => ({ product, offer: bestOfferOf(product, offersByProduct, conditions) }))
    .filter((m): m is { product: Product; offer: Offer } => m.offer !== null);
  const cheapest = priced.length
    ? priced.reduce((a, b) => (b.offer.price_cents! < a.offer.price_cents! ? b : a))
    : null;
  const prices = priced.map((m) => m.offer.price_cents!);
  const min = prices.length ? Math.min(...prices) : null;
  const max = prices.length ? Math.max(...prices) : null;
  const photoProduct = cheapest?.product ?? group.members[0];

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current!;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (openerRef.current?.isConnected) openerRef.current.focus();
    };
  }, [open]);

  return (
    <article className="product-card compact-product product-range-card">
      <button className="product-open" aria-label={`${group.name}, ${group.members.length} tamanhos`} onClick={() => setOpen(true)} ref={openerRef}>
        <ProductPhoto product={photoProduct} />
        <div className="product-summary">
          <h3>{group.name}</h3>
          <span className="product-pack">{group.members.length} tamanhos disponíveis</span>
          {min !== null && max !== null ? (
            <div className="product-price-line">
              <strong className="price range-price">
                {min === max ? money(min) : `${money(min)} – ${money(max)}`}
              </strong>
            </div>
          ) : (
            <span className="no-price">Sem preço atual</span>
          )}
        </div>
      </button>
      <button type="button" className="product-compare" onClick={() => setOpen(true)}>
        <span>Comparar tamanhos</span>
        <span>
          Ver os {group.members.length} <ChevronRight size={14} />
        </span>
      </button>
      {open && (
        <dialog
          ref={dialogRef}
          className="location-dialog range-dialog"
          aria-labelledby={titleId}
          onCancel={(event) => {
            event.preventDefault();
            setOpen(false);
          }}
          onClick={(event) => {
            if (event.target === dialogRef.current) setOpen(false);
          }}
        >
          <div className="location-dialog-heading">
            <div>
              <span className="eyebrow green-text">TAMANHOS DE {group.name.toUpperCase()}</span>
              <h2 id={titleId}>Escolha o tamanho</h2>
            </div>
            <button className="icon-button" onClick={() => setOpen(false)} aria-label="Fechar">
              <X size={21} />
            </button>
          </div>
          <ul className="size-rows">
            {group.members.map((product) => (
              <SizeRow
                key={product.id}
                product={product}
                offer={bestOfferOf(product, offersByProduct, conditions)}
                nearby={nearby}
                locationsByRetailer={locationsByRetailer}
                onOpen={() => {
                  setOpen(false);
                  onOpen(product);
                }}
                onAdd={() => onAdd(product)}
              />
            ))}
          </ul>
        </dialog>
      )}
    </article>
  );
}
