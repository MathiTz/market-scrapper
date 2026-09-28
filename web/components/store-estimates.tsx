import { TriangleAlert } from "lucide-react";
import { money } from "@/lib/domain";
import type { StoreEstimate } from "@/lib/estimates";
import { distanceLabel } from "@/lib/location";
import { Money } from "@/components/ui/number";

/**
 * One expandable card per chain: the total up front, the items behind it when opened. A chain that prices
 * the whole list shows a total; one that misses items shows a subtotal of what it does price, labelled and
 * styled as such, so a partial list never reads as the cheaper one just because it is missing things.
 */
export function StoreEstimates({
  estimates,
  total,
  nameOf,
  hasReference,
}: {
  estimates: StoreEstimate[];
  /** How many lines the list has. */
  total: number;
  nameOf: (productId: string) => string;
  hasReference: boolean;
}) {
  const complete = estimates.filter((s) => s.complete).length;
  return (
    <>
      {estimates.length > 0 && complete === 0 && (
        <p className="notice amber estimate-warning" role="note">
          <TriangleAlert size={18} aria-hidden="true" />
          <span>
            Nenhuma rede tem preço atual para todos os {total} itens. Os valores abaixo são subtotais parciais,
            de itens diferentes, e não devem ser comparados entre si.
          </span>
        </p>
      )}
      {estimates.map((store) => {
        const covered = store.items.filter((i) => i.offer);
        const missing = store.items.filter((i) => !i.offer);
        return (
          <details
            className={`basket-total basket-detail${store.complete ? "" : " partial"}`}
            key={store.context_id}
          >
            <summary>
              <div>
                <h3>{store.label}</h3>
                <p>
                  {store.complete
                    ? `Todos os ${total} itens com preço atual`
                    : `${store.covered} de ${total} itens com preço · ${missing.length === 1 ? "falta 1 item" : `faltam ${missing.length} itens`}`}
                  {store.distanceKm !== null && ` · unidade mais próxima ${distanceLabel(store.distanceKm)}`}
                </p>
                {(store.cheapest || store.nearest) && (
                  <p className="badges">
                    {store.cheapest && <span className="badge good">Menor total para a lista completa</span>}
                    {store.nearest && <span className="badge near">Mais perto da referência</span>}
                  </p>
                )}
              </div>
              <span className="basket-amount">
                <small>{store.complete ? "Total estimado" : "Subtotal parcial"}</small>
                <strong>
                  <Money cents={store.total} />
                </strong>
              </span>
            </summary>
            <ul className="basket-items">
              {covered.map((item) => (
                <li key={item.product_id}>
                  <span>{nameOf(item.product_id)}</span>
                  <span className="item-price">
                    {item.quantity} × {money(item.offer!.price_cents!)} ={" "}
                    <strong>{money(item.offer!.price_cents! * item.quantity)}</strong>
                  </span>
                </li>
              ))}
              {missing.map((item) => (
                <li key={item.product_id} className="missing">
                  <span>{nameOf(item.product_id)}</span>
                  <span className="item-price">Sem preço atual nesta rede · não somado</span>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
      {estimates.length > 0 && !hasReference && (
        <p className="fineprint">
          Defina seu local em “Perto de você” para ver a distância até a unidade mais próxima de cada rede.
        </p>
      )}
    </>
  );
}
