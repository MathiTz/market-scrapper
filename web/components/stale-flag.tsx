import { TriangleAlert } from "lucide-react";
import type { Offer } from "@/lib/domain";
import { staleNotice } from "@/lib/comparison";
import { Tooltip } from "@/components/ui/tooltip";

/**
 * The marker next to a price its store has not confirmed lately: "Não atualizado desde <date and time>" on
 * hover. A span, not a button, so it can sit inside a card's own button; the same sentence is also in its
 * accessible name, and the places that show the price print the date as text too, because a tooltip alone
 * does not reach a touch screen (see Tooltip: prices and dates must be readable without a pointer).
 */
export function StaleFlag({ offer }: { offer: Pick<Offer, "price_observed_at"> }) {
  const notice = staleNotice(offer);
  return (
    <Tooltip label={notice}>
      <span className="stale-flag" role="img" aria-label={notice}>
        <TriangleAlert size={14} aria-hidden="true" />
      </span>
    </Tooltip>
  );
}
