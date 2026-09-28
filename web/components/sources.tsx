import { ArrowUpRight, Store } from "lucide-react";
import { rankOffers, type Offer } from "@/lib/domain";
import { count, whenLabel } from "@/lib/format";

type Retailer = { id: string; name: string; official_url: string; last_error: string | null };

/**
 * "Como ler os preços" and the chains behind them: what the data is and is not, from the snapshot itself
 * (the freshness window is the offers' own ttl_hours, not a number written here).
 */
export function Sources({
  retailers,
  offers,
  demo,
}: {
  retailers: Retailer[];
  offers: Offer[];
  demo: boolean;
}) {
  const ttl = offers.find((o) => o.ttl_hours > 0)?.ttl_hours;
  const current = rankOffers(offers, true);
  const currentBy = new Map<string, number>();
  for (const o of current) currentBy.set(o.retailer_id, (currentBy.get(o.retailer_id) ?? 0) + 1);
  const latestBy = new Map<string, string>();
  for (const o of offers) {
    const seen = latestBy.get(o.retailer_id);
    if (!seen || Date.parse(o.price_observed_at) > Date.parse(seen)) latestBy.set(o.retailer_id, o.price_observed_at);
  }
  return (
    <section id="sources" className="sources" aria-labelledby="sources-title">
      <div className="section-heading">
        <h2 id="sources-title">Como ler os preços</h2>
        <span className="badge">{demo ? "Demonstração" : "Piloto"}</span>
      </div>
      <ul className="method-list">
        <li>
          {demo
            ? "Todos os preços e lojas desta demonstração são fictícios."
            : "Os preços vêm dos sites e encartes das próprias redes, lidos automaticamente. São preços do site: não foram confirmados em uma loja física."}
        </li>
        <li>
          Cada preço mostra quando foi visto.
          {ttl ? ` Um preço que não é visto de novo em ${ttl} h sai da comparação.` : ""}
        </li>
        <li>
          Preços de clube, cupom ou quantidade mínima aparecem com a condição e só entram na comparação quando
          você escolhe incluí-los.
        </li>
        <li>
          “Mesmo produto” considera o nome e o tamanho da embalagem. Diferenças de preço muito grandes são
          sinalizadas para você conferir a embalagem na origem.
        </li>
        <li>
          Distâncias são em linha reta até a unidade cadastrada mais próxima da referência que você escolher,
          não o trajeto.
        </li>
        <li>
          Não há reserva, entrega ou garantia de estoque. A compra é feita diretamente com a loja. Sua lista e
          sua localização ficam apenas neste navegador.
        </li>
      </ul>
      <h3 className="sources-subtitle">Redes acompanhadas</h3>
      {retailers.map((r) => {
        const n = currentBy.get(r.id) ?? 0;
        const latest = latestBy.get(r.id);
        return (
          <div key={r.id} className="source-row">
            <Store size={19} aria-hidden="true" />
            <div>
              <strong>{r.name}</strong>
              <span>
                {r.last_error
                  ? "A última coleta teve problema; mantida a lista anterior"
                  : demo
                    ? "Fictício"
                    : "Coleta automática"}
                {n > 0
                  ? ` · ${count(n)} ${n === 1 ? "preço atual" : "preços atuais"}`
                  : " · sem preço atual; somente encartes ou dados antigos"}
                {latest && ` · visto ${whenLabel(latest)}`}
              </span>
            </div>
            {r.official_url && !demo && (
              <a href={r.official_url} target="_blank" rel="noreferrer" aria-label={`Site oficial de ${r.name} (abre em nova aba)`}>
                <ArrowUpRight size={20} aria-hidden="true" />
              </a>
            )}
          </div>
        );
      })}
    </section>
  );
}
