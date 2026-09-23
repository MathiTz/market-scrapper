import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { ArrowUpRight, MapPin, X } from "lucide-react";
import { conditionLabel, money, type Offer } from "@/lib/domain";
import { StoreContact } from "@/components/store-contact";
import { OfferShare } from "@/components/offer-share";

function LocationDialog({
  offer,
  productName,
  onClose,
  opener,
  region,
  address,
}: {
  offer: Offer;
  productName: string;
  onClose: () => void;
  opener: RefObject<HTMLButtonElement | null>;
  region: string;
  address: string | null;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const demo = offer.method === "demo";
  const mapUrl =
    !demo && address
      ? `https://www.google.com/maps/search/?${new URLSearchParams({
          api: "1",
          query: `${offer.retailer_name}, ${address}`,
        })}`
      : null;

  useEffect(() => {
    const dialog = ref.current!;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (opener.current?.isConnected) opener.current.focus();
    };
  }, [opener]);

  return (
    <dialog
      ref={ref}
      className="location-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="location-dialog-heading">
        <h2 id={titleId}>Localização da loja</h2>
        <button
          className="icon-button"
          aria-label="Fechar localização"
          onClick={onClose}
          autoFocus
        >
          <X size={22} />
        </button>
      </div>
      <p className="location-retailer">{offer.retailer_name}</p>
      <StoreContact offer={offer} address={address} />
      <div className="location-offer">
        <strong>
          {productName} · {money(offer.price_cents!)}
        </strong>
        <p>
          {offer.channel === "catalog"
            ? "Preço online"
            : offer.channel === "physical"
              ? "Preço de loja física"
              : "Preço de encarte"}{" "}
          · {conditionLabel(offer.conditions)}
        </p>
        {offer.channel === "catalog" && (
          <p>
            Confirme com a loja se o preço online também se aplica à compra
            presencial.
          </p>
        )}
      </div>
      {demo ? (
        <p className="location-note">
          <strong>Localização fictícia.</strong> Este endereço é apenas
          demonstrativo e não indica uma loja real.
        </p>
      ) : mapUrl ? (
        <a
          className="primary location-map"
          href={mapUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Abrir no mapa <ArrowUpRight size={18} aria-hidden="true" />
        </a>
      ) : (
        <p className="location-note">
          A localização ficará disponível quando o endereço desta unidade for
          informado.
        </p>
      )}
      <OfferShare offer={offer} productName={productName} region={region} />
    </dialog>
  );
}

export function StoreLocation({
  offer,
  productName,
  region,
  address,
}: {
  offer: Offer;
  productName: string;
  region: string;
  /** The chain's real branch nearest to wherever is relevant right now (see lib/location.ts's offerLocation). */
  address: string | null;
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={opener}
        className="store-location-trigger"
        onClick={() => setOpen(true)}
      >
        <MapPin size={17} aria-hidden="true" /> Ver localização
      </button>
      {open && (
        <LocationDialog
          offer={offer}
          productName={productName}
          region={region}
          address={address}
          opener={opener}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
