import { money, type Offer } from "@/lib/domain";

/** The undiscounted price and the store's deal label ("25% OFF", "Leve 3 e pague 2"), when known. */
export function DealNote({ offer }: { offer: Offer }) {
  if (!offer.regular_price_cents && !offer.deal_label) return null;
  return (
    <span className="deal-note">
      {offer.regular_price_cents ? (
        <s aria-label={`Preço sem desconto ${money(offer.regular_price_cents)}`}>
          {money(offer.regular_price_cents)}
        </s>
      ) : null}
      {offer.deal_label ? <em>{offer.deal_label}</em> : null}
    </span>
  );
}
