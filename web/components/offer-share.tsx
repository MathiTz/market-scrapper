import { useRef, useState } from "react";
import { Share2 } from "lucide-react";
import {
  BRAND,
  conditionLabel,
  localTime,
  money,
  type Offer,
} from "@/lib/domain";
import { channelLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { capture } from "@/app/posthog";

type OfferShareProps = {
  offer: Offer;
  productName: string;
  region?: string;
  compact?: boolean;
};

export function OfferShare(props: OfferShareProps) {
  return (
    <ShareAction
      key={JSON.stringify([
        props.offer.product_id,
        props.offer.id,
        props.offer.method,
        props.region ?? BRAND.city,
      ])}
      {...props}
    />
  );
}

function ShareAction({
  offer,
  productName,
  region = BRAND.city,
  compact = false,
}: OfferShareProps) {
  const [status, setStatus] = useState("");
  const [manualLink, setManualLink] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function share() {
    const captureShare = (shareMethod: "native" | "clipboard") =>
      capture("offer_shared", {
        product_id: offer.product_id,
        offer_id: offer.id,
        retailer_id: offer.retailer_id,
        offer_channel: offer.channel,
        share_method: shareMethod,
      });
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setStatus("");
    setManualLink("");
    const demo = offer.method === "demo";
    const url = new URL(demo ? "/demo" : "/", window.location.origin);
    url.search = new URLSearchParams({
      produto: offer.product_id,
      oferta: offer.id,
      regiao: region,
    }).toString();
    const data: ShareData = {
      title: `${demo ? "Demonstração · " : ""}${productName} · ${BRAND.name}`,
      text: [
        demo ? "Dados fictícios — demonstração." : "",
        `${productName} · ${money(offer.price_cents!)} · ${offer.retailer_name}`,
        offer.context_label,
        // The same scope and conditions as on screen, so the message cannot promise more than the offer.
        `${channelLabel(offer.channel)}${offer.channel === "catalog" ? " (confirme na loja)" : ""}`,
        conditionLabel(offer.conditions),
        `Visto em ${localTime(offer.price_observed_at)}`,
      ]
        .filter(Boolean)
        .join("\n"),
      url: url.href,
    };
    try {
      if (navigator.share) {
        try {
          await navigator.share(data);
          captureShare("native");
          return;
        } catch (error) {
          if ((error as { name?: string })?.name === "AbortError") return;
        }
      }
      try {
        await navigator.clipboard.writeText(url.href);
        captureShare("clipboard");
        setStatus("Link copiado para compartilhar.");
      } catch {
        setManualLink(url.href);
        setStatus("Copie o link abaixo para compartilhar.");
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <div className={`offer-share${compact ? " compact-share" : ""}`}>
      {compact ? (
        // Icon only on cards: the tooltip (components/ui/tooltip.tsx) shows the name a sighted person needs.
        <Tooltip label="Compartilhar">
          <Button
            variant="secondary"
            iconOnly
            className="share-offer-button"
            aria-label="Compartilhar oferta"
            icon={<Share2 size={18} aria-hidden="true" />}
            onClick={share}
            loading={busy}
          />
        </Tooltip>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="share-offer-button"
          aria-label="Compartilhar oferta"
          icon={<Share2 size={18} aria-hidden="true" />}
          onClick={share}
          loading={busy}
        >
          Compartilhar
        </Button>
      )}
      {status && (
        <p className="offer-share-status" role="status">
          {status}
        </p>
      )}
      {manualLink && (
        <label className="offer-share-copy">
          Link para compartilhar
          <input
            readOnly
            value={manualLink}
            onFocus={(event) => event.currentTarget.select()}
          />
        </label>
      )}
    </div>
  );
}
