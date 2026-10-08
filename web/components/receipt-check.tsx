import { useEffect, useId, useRef, useState } from "react";
import { ReceiptText, TriangleAlert, Upload } from "lucide-react";
import { capture } from "@/app/posthog";
import { money, type Offer, type Product } from "@/lib/domain";
import {
  compareReceipt,
  type ListLine,
  type PriceVerdict,
  type ReceiptComparison,
  type ReceiptReport,
  type ReceiptResult,
} from "@/lib/receipt";
import { readReceipt, receiptFileProblem, ReceiptError, RECEIPT_TYPES } from "@/lib/receipt-api";
import { Button } from "@/components/ui/button";

type State =
  | { status: "idle" }
  | { status: "reading" }
  | { status: "done"; report: ReceiptReport; degraded: boolean; hasBadMath: boolean; lines: number }
  | { status: "error"; message: string };

const verdicts: Record<PriceVerdict, { label: string; tone: "green" | "amber" | "" }> = {
  inside: { label: "Dentro do que vimos", tone: "green" },
  above: { label: "Acima do que vimos", tone: "amber" },
  below: { label: "Abaixo do que vimos", tone: "" },
  "no-price": { label: "Sem preço atual para comparar", tone: "" },
};

const quantity = (n: number) => n.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
const reais = (value: number | null) => (value == null ? "" : money(Math.round(value * 100)));

function Row({ c }: { c: ReceiptComparison }) {
  const verdict = verdicts[c.verdict];
  const { item } = c;
  return (
    <li className="receipt-row">
      <div className="receipt-row-main">
        <strong>{c.productName}</strong>
        <span className="receipt-line-text">
          No cupom: {item.name}
          {item.qty != null && item.unit_price != null && ` · ${quantity(item.qty)} × ${reais(item.unit_price)}`}
        </span>
      </div>
      <div className="receipt-row-price">
        {c.paidCents != null && <strong className="price">{money(c.paidCents)}</strong>}
        <span className={`badge ${verdict.tone}`}>{verdict.label}</span>
        {c.cheapestCents != null && c.highestCents != null && (
          <span className="muted receipt-range">
            Menor preço atual: {money(c.cheapestCents)}
            {c.cheapestRetailer && ` (${c.cheapestRetailer})`}
            {c.highestCents !== c.cheapestCents && ` · vai até ${money(c.highestCents)}`}
          </span>
        )}
        {c.verdict === "below" && (
          <span className="muted receipt-range">O preço que temos pode estar desatualizado.</span>
        )}
      </div>
    </li>
  );
}

function summary(report: ReceiptReport, lines: number): string {
  const matched = report.comparisons.length;
  if (!matched) return "Nenhuma linha do cupom corresponde a itens da sua lista.";
  const found = `${matched} de ${lines} ${lines === 1 ? "linha" : "linhas"} do cupom ${matched === 1 ? "corresponde" : "correspondem"} a itens da sua lista.`;
  if (report.overpaidCents > 0)
    return `${found} Nesses itens você pagou ${money(report.overpaidCents)} a mais que o menor preço que temos.`;
  const compared = report.comparisons.filter((c) => c.verdict !== "no-price").length;
  return compared
    ? `${found} Você não pagou acima do menor preço que temos nesses itens.`
    : `${found} Não temos preço atual para compará-las.`;
}

/**
 * "Conferir com o cupom", on the shopping list: a photo of the receipt goes to POST /api/receipt/ocr, and
 * each line read is compared with the prices we have for the items on the list (lib/receipt.ts). Only
 * rendered where the route exists (see `receiptOcrEnabled` in lib/receipt-api.ts).
 */
export function ReceiptCheck({
  lines,
  productById,
  offers,
  disabledReason,
}: {
  lines: ListLine[];
  productById: Map<string, Product>;
  offers: Offer[];
  /** Why the check cannot run right now (offline, prices not loaded), shown instead of a dead button. */
  disabledReason?: string;
}) {
  const [state, setState] = useState<State>({ status: "idle" });
  const input = useRef<HTMLInputElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const request = useRef<AbortController | null>(null);
  const titleId = useId();

  useEffect(() => () => request.current?.abort(), []);
  // The result is new content below the button: move focus to it so a keyboard or screen reader user lands there.
  useEffect(() => {
    if (state.status === "done") resultHeading.current?.focus({ preventScroll: false });
  }, [state.status]);

  async function check(file: File) {
    const problem = receiptFileProblem(file);
    if (problem) {
      setState({ status: "error", message: problem });
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setState({ status: "reading" });
    let result: ReceiptResult;
    try {
      result = await readReceipt(file, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return; // cancelled, or a newer photo replaced this one
      const failure = error instanceof ReceiptError ? error : null;
      capture("receipt_check_failed", { failure_kind: failure?.kind ?? "unknown" });
      setState({ status: "error", message: failure?.message ?? "Não foi possível ler o cupom agora." });
      return;
    }
    const report = compareReceipt(result, lines, productById, offers);
    capture("receipt_check_completed", {
      receipt_lines: result.items.length,
      matched_lines: report.comparisons.length,
      degraded: result.degraded,
    });
    setState({
      status: "done",
      report,
      degraded: result.degraded || result.flags.missing_lines.length > 0,
      hasBadMath: result.flags.bad_math.length > 0,
      lines: result.items.length,
    });
  }

  const reading = state.status === "reading";
  return (
    <section className="receipt-check" aria-labelledby={titleId}>
      <div className="receipt-intro">
        <ReceiptText size={26} strokeWidth={1.4} aria-hidden="true" />
        <div>
          <h2 id={titleId}>Conferir com o cupom</h2>
          <p>
            Já fez as compras? Envie uma foto do cupom fiscal e comparamos o que você pagou com os preços que temos para
            os itens da sua lista.
          </p>
        </div>
      </div>
      <p className="fineprint">
        A foto é enviada ao serviço de leitura de imagens (ollama.com) só para reconhecer os itens, e não é guardada por
        nós. O cupom pode mostrar CPF, endereço da loja e dados de pagamento: cubra o que não quiser enviar.
      </p>
      <input
        ref={input}
        type="file"
        accept={RECEIPT_TYPES.join(",")}
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = ""; // the same photo can be picked again
          if (file) void check(file);
        }}
      />
      <div className="receipt-actions">
        <Button
          variant="primary"
          icon={<Upload size={17} aria-hidden="true" />}
          loading={reading}
          disabled={!!disabledReason}
          onClick={() => input.current?.click()}
        >
          {reading ? "Lendo o cupom…" : state.status === "done" ? "Enviar outro cupom" : "Enviar foto do cupom"}
        </Button>
        {reading && (
          <Button
            variant="ghost"
            onClick={() => {
              request.current?.abort();
              setState({ status: "idle" });
            }}
          >
            Cancelar
          </Button>
        )}
      </div>
      {disabledReason && <p className="muted">{disabledReason}</p>}
      <div role="status" aria-live="polite">
        {reading && <p className="muted">Lendo as linhas do cupom. Costuma levar cerca de um minuto.</p>}
      </div>
      {state.status === "error" && (
        <div className="notice amber" role="alert">
          <TriangleAlert size={19} aria-hidden="true" />
          <span>{state.message}</span>
        </div>
      )}
      {state.status === "done" && (
        <div className="receipt-result">
          <h3 ref={resultHeading} tabIndex={-1}>
            Resultado da conferência
          </h3>
          <p className="receipt-summary">{summary(state.report, state.lines)}</p>
          {state.degraded && (
            <div className="notice amber">
              <TriangleAlert size={19} aria-hidden="true" />
              <span>
                Parte do cupom não foi lida (foto cortada, borrada ou com reflexo). A conferência pode estar incompleta:
                tente de novo com uma foto mais nítida.
              </span>
            </div>
          )}
          {state.hasBadMath && (
            <div className="notice amber">
              <TriangleAlert size={19} aria-hidden="true" />
              <span>Em algumas linhas a conta não fecha com o que foi lido. Confira os valores com o cupom.</span>
            </div>
          )}
          {state.report.comparisons.length > 0 && (
            <ul className="receipt-rows">
              {state.report.comparisons.map((c, index) => (
                <Row key={`${c.productId}-${index}`} c={c} />
              ))}
            </ul>
          )}
          {state.report.unmatched.length > 0 && (
            <details className="receipt-more">
              <summary>
                {state.report.unmatched.length}{" "}
                {state.report.unmatched.length === 1 ? "linha do cupom não está" : "linhas do cupom não estão"} na sua
                lista
              </summary>
              <ul>
                {state.report.unmatched.map((item, index) => (
                  <li key={index}>
                    {item.name}
                    {item.total != null && ` · ${reais(item.total)}`}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {state.report.notOnReceipt.length > 0 && (
            <details className="receipt-more">
              <summary>
                {state.report.notOnReceipt.length}{" "}
                {state.report.notOnReceipt.length === 1 ? "item da lista não aparece" : "itens da lista não aparecem"} no
                cupom
              </summary>
              <ul>
                {state.report.notOnReceipt.map((item) => (
                  <li key={item.productId}>{item.name}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
