import { money } from "@/lib/domain";
import type { StoreEstimate } from "@/lib/estimates";
import { distanceLabel } from "@/lib/location";

type Line = { product_id: string; name: string; quantity: number };

/** One expandable card per store: the total up front, the items behind it when opened. */
export function StoreEstimates({
  estimates,
  lines,
  hasReference,
}: {
  estimates: StoreEstimate[];
  lines: Line[];
  hasReference: boolean;
}) {
  const nameOf = new Map(lines.map((l) => [l.product_id, l.name]));
  return (
    <>
      {estimates.map((store) => {
        const covered = store.items.filter((i) => i.offer);
        const missing = store.items.filter((i) => !i.offer);
        return (
          <details className="basket-total basket-detail" key={store.context_id}>
            <summary>
              <div>
                <h3>{store.label}</h3>
                <p>
                  {store.covered} de {lines.length} itens cobertos ·{" "}
                  {store.complete ? "Todos os itens com preço" : "Subtotal parcial"}
                  {store.distanceKm !== null && ` · ${distanceLabel(store.distanceKm)}`}
                </p>
                {(store.cheapest || store.nearest) && (
                  <p className="badges">
                    {store.cheapest && <span className="badge good">Mais barato</span>}
                    {store.nearest && <span className="badge near">Mais perto</span>}
                  </p>
                )}
              </div>
              <strong>{money(store.total)}</strong>
            </summary>
            <ul className="basket-items">
              {covered.map((item) => (
                <li key={item.product_id}>
                  <span>{nameOf.get(item.product_id)}</span>
                  <span className="item-price">
                    {item.quantity} × {money(item.offer!.price_cents!)} ={" "}
                    <strong>{money(item.offer!.price_cents! * item.quantity)}</strong>
                  </span>
                </li>
              ))}
              {missing.map((item) => (
                <li key={item.product_id} className="missing">
                  <span>{nameOf.get(item.product_id)}</span>
                  <span className="item-price">
                    {item.product_id.startsWith("note:")
                      ? "Anotação, sem preço"
                      : "Sem preço nesta loja"}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
      {estimates.length > 0 && !hasReference && (
        <p className="fineprint">
          Defina seu local em “Perto de você” para destacar a loja mais próxima.
        </p>
      )}
    </>
  );
}
