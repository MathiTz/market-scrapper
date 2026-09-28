import { useId, useRef, useState } from "react";
import { ChevronRight, Plus, X } from "lucide-react";
import { money, rankOffers, unitPrice, type Offer, type Product } from "@/lib/domain";
import type { ProductGroup } from "@/lib/group";
import { knownSize, packLabel, unitPriceText } from "@/lib/format";
import { offerLocation, distanceLabel, type LocationsByRetailer, type Nearby } from "@/lib/location";
import { ProductPhoto } from "./product-card";
import { IconButton } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useDialog } from "@/components/ui/use-dialog";
import { useSheetDrag } from "@/components/ui/use-sheet-drag";

/** A group member's own best current offer, resolved once and shared by the card and its modal row. */
function bestOfferOf(product: Product, offersByProduct: Map<string, Offer[]>, conditions: boolean) {
  return rankOffers(offersByProduct.get(product.id) ?? [], conditions)[0] ?? null;
}

const totalSize = (p: Product) => p.amount * p.pack_count;

/**
 * The member with the lowest price per kg/L/unit, when every priced member is measured the same way (all in
 * grams, all in millilitres or all counted) - comparing a per-kg with a per-unit figure would mean nothing.
 */
function bestValue(priced: { product: Product; offer: Offer }[]) {
  const measurable = priced.filter((m) => knownSize(m.product));
  if (measurable.length < 2 || new Set(measurable.map((m) => m.product.unit)).size !== 1) return null;
  return measurable.reduce((a, b) =>
    unitPrice(b.product, b.offer.price_cents!).value < unitPrice(a.product, a.offer.price_cents!).value ? b : a,
  );
}

function SizeRow({
  product,
  offer,
  best,
  nearby,
  locationsByRetailer,
  onOpen,
  onAdd,
}: {
  product: Product;
  offer: Offer | null;
  best: boolean;
  nearby: Nearby | null;
  locationsByRetailer: LocationsByRetailer;
  onOpen: () => void;
  onAdd: () => void;
}) {
  const found = offer && nearby ? offerLocation(offer, locationsByRetailer, nearby.point) : null;
  const unit = offer ? unitPriceText(product, offer.price_cents!, { repeat: true }) : null;
  return (
    <li className={`size-row${best ? " best-value" : ""}`}>
      <button type="button" className="size-row-open" onClick={onOpen}>
        <span className="size-row-pack">{packLabel(product)}</span>
        {offer ? (
          <>
            <strong>{money(offer.price_cents!)}</strong>
            {unit && <span className="unit-price">{unit}</span>}
            {best && <span className="badge green">Menor preço por {unitPrice(product, 1).unit}</span>}
            <span className="muted">
              {offer.retailer_name}
              {found && ` · ${distanceLabel(found.distanceKm)}`}
            </span>
          </>
        ) : (
          <span className="no-price">Sem preço atual</span>
        )}
      </button>
      {offer && (
        <button type="button" className="size-row-add" aria-label={`Adicionar ${product.name} à lista`} onClick={onAdd}>
          <Plus size={16} aria-hidden="true" />
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
  const openerRef = useRef<HTMLButtonElement>(null);
  const { ref: dialogRef, requestClose } = useDialog(open, () => setOpen(false), openerRef);
  useSheetDrag(dialogRef, requestClose);
  const titleId = useId();

  // Smallest pack first, in the dialog and in the card's list of sizes.
  const members = [...group.members].sort((a, b) =>
    a.unit === b.unit ? totalSize(a) - totalSize(b) : a.unit.localeCompare(b.unit),
  );
  const rows = members.map((product) => ({ product, offer: bestOfferOf(product, offersByProduct, conditions) }));
  const priced = rows.filter((m): m is { product: Product; offer: Offer } => m.offer !== null);
  const cheapest = priced.length
    ? priced.reduce((a, b) => (b.offer.price_cents! < a.offer.price_cents! ? b : a))
    : null;
  const value = bestValue(priced);
  const photoProduct = cheapest?.product ?? members[0];
  const sizes = members.map((p) => packLabel(p)).join(", ");

  return (
    <article
      className="product-card compact-product product-range-card"
      data-product-id={members.map((p) => p.id).join(" ")}
    >
      <button
        className="product-open"
        aria-label={`${group.name}, ${members.length} tamanhos: ${sizes}.${cheapest ? ` A partir de ${money(cheapest.offer.price_cents!)}, na embalagem de ${packLabel(cheapest.product)}.` : " Sem preço atual."} Comparar tamanhos`}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
        ref={openerRef}
      >
        <ProductPhoto product={photoProduct} />
        <div className="product-summary">
          <h3>{group.name}</h3>
          <span className="product-pack">
            {members.length} tamanhos: {sizes}
          </span>
          {cheapest ? (
            <div className="product-price-line">
              <span className="range-from">a partir de</span>
              <strong className="price range-price">{money(cheapest.offer.price_cents!)}</strong>
              <span className="muted unit-price">na embalagem de {packLabel(cheapest.product)}</span>
            </div>
          ) : (
            <span className="no-price">Sem preço atual</span>
          )}
        </div>
      </button>
      {value && (
        <p className="range-value">
          Menor preço por {unitPrice(value.product, 1).unit}: {unitPriceText(value.product, value.offer.price_cents!, { repeat: true })}{" "}
          ({packLabel(value.product)}, {value.offer.retailer_name})
        </p>
      )}
      <button type="button" className="product-compare" onClick={() => setOpen(true)} aria-haspopup="dialog">
        <span>Comparar os {members.length} tamanhos</span>
        <ChevronRight size={14} aria-hidden="true" />
      </button>
      {open && (
        <dialog
          ref={dialogRef}
          className="location-dialog range-dialog"
          data-sheet=""
          aria-labelledby={titleId}
          onCancel={(event) => {
            event.preventDefault();
            requestClose();
          }}
          onClick={(event) => {
            if (event.target === dialogRef.current) requestClose();
          }}
        >
          <div className="location-dialog-heading" data-sheet-grip="">
            <div>
              <p className="overline">Tamanhos diferentes</p>
              <h2 id={titleId}>{group.name}</h2>
            </div>
            <Tooltip label="Fechar">
              <IconButton label="Fechar" onClick={() => requestClose()}>
                <X size={21} aria-hidden="true" />
              </IconButton>
            </Tooltip>
          </div>
          <div className="sheet-body" data-scroll="">
          <p className="range-note">
            Embalagens diferentes do mesmo produto, com o menor preço atual de cada uma. Compare pelo preço por
            kg, litro ou unidade.
          </p>
          <ul className="size-rows">
            {rows.map(({ product, offer }) => (
              <SizeRow
                key={product.id}
                product={product}
                offer={offer}
                best={!!value && value.product.id === product.id}
                nearby={nearby}
                locationsByRetailer={locationsByRetailer}
                onOpen={() => {
                  requestClose();
                  onOpen(product);
                }}
                // The toast lives outside the top layer: the dialog closes first so the confirmation is seen.
                onAdd={() => {
                  requestClose();
                  onAdd(product);
                }}
              />
            ))}
          </ul>
          </div>
        </dialog>
      )}
    </article>
  );
}
