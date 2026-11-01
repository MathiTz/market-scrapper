import { useId } from "react";
import { money } from "@/lib/domain";
import { listName, unitPriceText } from "@/lib/format";
import type { BasketReport, ChainBasket } from "@/lib/receipt-basket";

const difference = (paid: number, total: number) =>
  paid === total
    ? "o mesmo que você pagou"
    : paid > total
      ? `${money(paid - total)} a menos do que você pagou`
      : `${money(total - paid)} a mais do que você pagou`;

const items = (n: number) => `${n} ${n === 1 ? "item" : "itens"}`;

function Chain({ chain, total }: { chain: ChainBasket; total: number }) {
  const covered = chain.lines.length;
  return (
    <li className={`receipt-chain${chain.missing.length ? " receipt-chain-partial" : ""}`}>
      <details>
        <summary>
          <span className="receipt-chain-name">{chain.retailerName}</span>
          <strong className="price">{money(chain.totalCents)}</strong>
          <span className="receipt-chain-note">
            {chain.missing.length
              ? `Só ${covered} de ${total} itens: ${difference(chain.paidCents, chain.totalCents)} ${covered === 1 ? "nesse item" : "nesses itens"}`
              : difference(chain.paidCents, chain.totalCents)}
          </span>
        </summary>
        <ul className="receipt-chain-lines">
          {chain.lines.map((line) => (
            <li key={`${line.comparison.productId}-${line.offer.id}`}>
              <span>
                {listName(line.product)}
                {line.kind === "similar" && <span className="badge"> Parecido</span>}
                <small className="muted">
                  {line.kind === "similar"
                    ? ` · ${unitPriceText(line.product, line.packCents, { repeat: true }) ?? ""} · pacote de ${money(line.packCents)}`
                    : ` · ${money(line.packCents)}`}
                </small>
              </span>
              <strong>{money(line.costCents)}</strong>
            </li>
          ))}
        </ul>
        {chain.missing.length > 0 && (
          <p className="muted receipt-chain-missing">
            Sem preço atual aqui: {chain.missing.map((m) => m.productName).join(", ")}.
          </p>
        )}
      </details>
    </li>
  );
}

/**
 * "Onde sairia mais barato": the lines of the receipt priced at each chain (lib/receipt-basket.ts), the
 * cheapest chain that has them all, and what buying each line where it is cheapest would have cost.
 */
export function ReceiptBasket({ report }: { report: BasketReport }) {
  const titleId = useId();
  if (!report.chains.length) return null;
  const { bestSingle, bestSplit } = report;
  const anySimilar = report.chains.some((c) => c.lines.some((l) => l.kind === "similar"));
  const fullest = report.chains[0];
  const splitHelps =
    bestSplit && bestSplit.chains.length > 1 && (!bestSingle || bestSplit.totalCents < bestSingle.totalCents);
  return (
    <section className="receipt-basket" aria-labelledby={titleId}>
      <h3 id={titleId}>Onde sairia mais barato</h3>
      <p className="receipt-summary">
        {bestSingle
          ? `Em ${bestSingle.retailerName}, os ${items(report.considered)} do cupom sairiam por ${money(bestSingle.totalCents)}: ${difference(bestSingle.paidCents, bestSingle.totalCents)}.`
          : `Nenhuma rede tem todos os ${items(report.considered)} do cupom com preço atual. A que mais tem é ${fullest.retailerName} (${fullest.lines.length} de ${report.considered}), por ${money(fullest.totalCents)}.`}
        {splitHelps &&
          ` Comprando cada item onde está mais barato, em ${bestSplit.chains.length} redes: ${money(bestSplit.totalCents)}, ${difference(bestSplit.paidCents, bestSplit.totalCents)}${bestSplit.lines < report.considered ? ` (${items(bestSplit.lines)} de ${report.considered})` : ""}.`}
      </p>
      <ul className="receipt-chains">
        {report.chains.map((chain) => (
          <Chain key={chain.retailerId} chain={chain} total={report.considered} />
        ))}
      </ul>
      {anySimilar && (
        <p className="fineprint">
          “Parecido” é outro produto do mesmo tipo, calculado pelo preço por kg ou litro para a quantidade que você
          levou: é uma estimativa, e o pacote à venda pode ser maior que o seu.
        </p>
      )}
    </section>
  );
}
