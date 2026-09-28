import { useId, useRef, useState, type RefObject } from "react";
import { ArrowUpRight, MapPin, X } from "lucide-react";
import { BRAND, conditionLabel, isConditional, money, type Offer } from "@/lib/domain";
import { channelLabel, count, whenLabel } from "@/lib/format";
import { distanceLabel, nearestLocation, type Nearby, type RetailerLocation } from "@/lib/location";
import { OfferShare } from "@/components/offer-share";
import { Button, IconButton, buttonClass } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useDialog } from "@/components/ui/use-dialog";
import { useSheetDrag } from "@/components/ui/use-sheet-drag";

const mapSearch = (query: string) =>
  `https://www.google.com/maps/search/?${new URLSearchParams({ api: "1", query })}`;

/**
 * Where to find the chain behind an offer. The price belongs to the chain's website, not to one branch:
 * the dialog says so first, and only names a branch - the nearest to the person's own reference - once
 * there is a reference. Without one it does not pick a branch on the person's behalf.
 */
function LocationDialog({
  offer,
  productName,
  onClose,
  opener,
  region,
  nearby,
  locations,
}: {
  offer: Offer;
  productName: string;
  onClose: () => void;
  opener: RefObject<HTMLButtonElement | null>;
  region: string;
  nearby: Nearby | null;
  locations: RetailerLocation[];
}) {
  // Mounted only while open: the hook shows the modal now and unmounts it (via onClose) after the exit.
  const { ref, requestClose } = useDialog(true, onClose, opener);
  useSheetDrag(ref, requestClose);
  const titleId = useId();
  const demo = offer.method === "demo";
  const found = nearby ? nearestLocation(locations, nearby.point) : null;
  const phone = offer.store_phone;

  return (
    <dialog
      ref={ref}
      className="location-dialog"
      data-sheet=""
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) requestClose();
      }}
    >
      <div className="location-dialog-heading" data-sheet-grip="">
        <div>
          <p className="overline">Onde encontrar</p>
          <h2 id={titleId}>{offer.retailer_name}</h2>
        </div>
        <Tooltip label="Fechar">
          <IconButton label="Fechar" onClick={() => requestClose()} autoFocus>
            <X size={22} aria-hidden="true" />
          </IconButton>
        </Tooltip>
      </div>
      <div className="sheet-body" data-scroll="">
      <div className="location-offer">
        <strong>
          {productName} · {money(offer.price_cents!)}
        </strong>
        <p>
          {channelLabel(offer.channel)} da rede, visto {whenLabel(offer.price_observed_at)}.
        </p>
        <p className={isConditional(offer.conditions) ? "location-condition" : undefined}>
          {conditionLabel(offer.conditions)}
        </p>
        {offer.channel === "catalog" && (
          <p>
            O preço não foi confirmado em uma unidade física. Confirme com a
            loja antes de ir.
          </p>
        )}
      </div>
      {demo ? (
        <p className="location-note">
          <strong>Localização fictícia.</strong> Os endereços da demonstração
          não indicam lojas reais.
        </p>
      ) : found ? (
        <div className="location-branch">
          <h3>
            Unidade mais próxima{" "}
            {nearby!.point.source === "device" ? "de você" : "da sua referência"}
          </h3>
          <p className="location-distance">
            <MapPin size={16} aria-hidden="true" /> {found.location.name} ·{" "}
            {distanceLabel(found.distanceKm)} em linha reta, não é o trajeto
          </p>
          <p>{found.location.address}</p>
          <a
            className={buttonClass("primary", "md", "location-map")}
            href={mapSearch(`${offer.retailer_name}, ${found.location.address}`)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir no mapa <ArrowUpRight size={18} aria-hidden="true" />
            <span className="sr-only"> (abre em nova aba)</span>
          </a>
        </div>
      ) : locations.length ? (
        <div className="location-branch">
          <p>
            A rede tem {count(locations.length)}{" "}
            {locations.length === 1 ? "unidade cadastrada" : "unidades cadastradas"}.
            Defina seu local em “Perto de você” para ver a mais próxima e a
            distância.
          </p>
          <a
            className={buttonClass("secondary", "md", "location-map")}
            href={mapSearch(`${offer.retailer_name} ${region || BRAND.city}`)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Procurar unidades no mapa <ArrowUpRight size={18} aria-hidden="true" />
            <span className="sr-only"> (abre em nova aba)</span>
          </a>
        </div>
      ) : (
        <p className="location-note">
          A fonte não informou os endereços das unidades desta rede.
        </p>
      )}
      <p className="location-phone">
        {phone ? (
          demo ? (
            <>Telefone {phone} · fictício</>
          ) : (
            <>
              Telefone: <a href={`tel:${phone.replace(/[^+\d]/g, "")}`}>{phone}</a>
            </>
          )
        ) : (
          "Telefone não informado pela fonte."
        )}
      </p>
      <OfferShare offer={offer} productName={productName} region={region} />
      </div>
    </dialog>
  );
}

export function StoreLocation({
  offer,
  productName,
  region,
  nearby,
  locations,
}: {
  offer: Offer;
  productName: string;
  region: string;
  nearby: Nearby | null;
  /** The chain's real branches (the snapshot's retailer_locations for this retailer). */
  locations: RetailerLocation[];
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Button
        ref={opener}
        variant="secondary"
        size="sm"
        className="store-location-trigger"
        aria-haspopup="dialog"
        icon={<MapPin size={17} aria-hidden="true" />}
        onClick={() => setOpen(true)}
      >
        Onde encontrar
      </Button>
      {open && (
        <LocationDialog
          offer={offer}
          productName={productName}
          region={region}
          nearby={nearby}
          locations={locations}
          opener={opener}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
