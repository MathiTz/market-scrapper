import { useEffect, useId, useRef, useState } from "react";
import { BookOpen, ArrowUpRight, Maximize2 } from "lucide-react";
import { flyerState, localTime, type Flyer } from "@/lib/domain";
import {
  organizeFlyers,
  flyerPeriod,
  flyerMonthLabel,
  flyerWeekLabel,
  flyerPages,
  flyerDateRange,
  flyerStates,
} from "@/lib/flyers";
import { FlyerDialog } from "./flyer-stories";
import {
  FlyerValidity,
  NetworkTabs,
  PageControls,
  PageProgress,
  useFlyerPlayer,
  useInView,
} from "./flyer-player";

export function FlyerCard({ f, flyers = [f] }: { f: Flyer; flyers?: Flyer[] }) {
  const opener = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState("");
  const [loaded, setLoaded] = useState("");
  const pages = flyerPages(f);
  const { ref, visible } = useInView();
  const [activeIndex, setActiveIndex] = useState(0);
  const player = useFlyerPlayer(
    pages.length,
    open || !visible || !loaded || loaded !== pages[activeIndex]?.url,
    0,
    true,
  );
  const page = pages[player.index];
  useEffect(() => setActiveIndex(player.index), [player.index]);
  const demo = f.method === "demo";
  const swipe = useRef<{ x: number; y: number } | null>(null);
  const swiped = useRef(false);
  return (
    <article
      className="flyer-card"
      ref={ref}
      aria-label={f.title + " · " + f.retailer_name}
      onMouseEnter={player.pause}
      onFocusCapture={(event) => {
        if (!(event.target as HTMLElement).closest(".story-play"))
          player.pause();
      }}
    >
      <div className="flyer-card-heading">
        <span className="flyer-network">{f.retailer_name}</span>
        <span
          className={"badge " + (flyerState(f) === "current" ? "green" : "")}
        >
          {demo ? "Fictício" : flyerStates[flyerState(f)]}
        </span>
      </div>
      <div className="flyer-card-player">
        <PageProgress player={player} count={pages.length} />
        <button
          ref={opener}
          className="flyer-open"
          onClick={() => {
            if (swiped.current) {
              swiped.current = false;
              return;
            }
            setOpen(true);
          }}
          aria-label={"Ver encarte " + f.title + " de " + f.retailer_name}
          onPointerDown={(event) => {
            swipe.current = { x: event.clientX, y: event.clientY };
            swiped.current = false;
          }}
          onPointerUp={(event) => {
            const start = swipe.current;
            swipe.current = null;
            if (
              start &&
              Math.abs(event.clientX - start.x) > 45 &&
              Math.abs(event.clientY - start.y) < 60
            ) {
              swiped.current = true;
              player.go(player.index + (event.clientX < start.x ? 1 : -1));
            }
          }}
          onPointerCancel={() => {
            swipe.current = null;
          }}
        >
          <div className="flyer-cover">
            {page?.type === "image" && failed !== page.url ? (
              <img
                key={page.url}
                src={page.url}
                alt={
                  "Ofertas de " +
                  f.retailer_name +
                  " · página " +
                  (player.index + 1) +
                  (demo ? " · dados fictícios" : "")
                }
                loading="lazy"
                draggable={false}
                onLoad={() => {
                  setLoaded(page.url);
                  setFailed("");
                }}
                onError={() => {
                  setFailed(page.url);
                  player.pause();
                }}
                referrerPolicy="no-referrer"
              />
            ) : (
              <>
                <BookOpen size={40} strokeWidth={1.2} />
                <span>{demo ? "ENCARTE FICTÍCIO" : "ENCARTE OFICIAL"}</span>
                <strong>{f.title}</strong>
                <small>
                  {failed
                    ? "Imagem indisponível · consulte a origem"
                    : "Consulte o documento original"}
                </small>
              </>
            )}
          </div>
          <span className="flyer-open-hint">
            <Maximize2 size={16} /> Ver encarte
          </span>
        </button>
        <PageControls player={player} count={pages.length} />
      </div>
      <div className="flyer-body">
        <h3>{f.title}</h3>
        <p className="flyer-dates">{flyerDateRange(f)}</p>
        <FlyerValidity flyer={f} />
        <p className="small">{f.scope}</p>
        {!demo && (
          <a
            className="text-link"
            href={f.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Abrir no site oficial <ArrowUpRight size={17} />
          </a>
        )}
        <span className="fineprint">
          {demo
            ? "Exemplo demonstrativo"
            : "Cadastro " +
              (f.method === "manual" ? "manual" : "automático")}{" "}
          · {localTime(f.collected_at)}
        </span>
      </div>
      {open && (
        <FlyerDialog
          f={f}
          flyers={flyers}
          initialPage={player.index}
          opener={opener}
          onClose={() => setOpen(false)}
        />
      )}
    </article>
  );
}

const categories = {
  current: "Válidos agora",
  future: "Em breve",
  unknown: "Sem validade confirmada",
  archived: "Arquivados",
};
type Category = keyof typeof categories;

export function FlyerBrowser({
  flyers,
  retailers,
}: {
  flyers: Flyer[];
  retailers: { id: string; name: string }[];
}) {
  const [category, setCategory] = useState<Category>("current");
  const [network, setNetwork] = useState("");
  const [month, setMonth] = useState("");
  const [week, setWeek] = useState("");
  const [now, setNow] = useState<Date | undefined>();
  const panelId = useId();
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  const organized = organizeFlyers(flyers, now);
  const archived = category === "archived";
  const editions = organized[category].filter(
    (f) => !network || f.retailer_id === network,
  );
  const months = [...new Set(editions.map((f) => flyerPeriod(f).month))]
    .sort()
    .reverse();
  const weeks = [
    ...new Set(
      editions
        .filter((f) => flyerPeriod(f).month === month)
        .map((f) => flyerPeriod(f).week),
    ),
  ].sort((a, b) => a - b);
  const shown = editions.filter(
    (f) =>
      !archived ||
      ((!month || flyerPeriod(f).month === month) &&
        (!week || flyerPeriod(f).week === Number(week))),
  );
  const networks = [
    { id: "", name: "Todas as redes", count: organized[category].length },
    ...retailers.map((r) => ({
      ...r,
      count: organized[category].filter((f) => f.retailer_id === r.id).length,
    })),
  ];
  return (
    <>
      <div className="page-title flyer-page-title">
        <h1>As ofertas, página a página.</h1>
        <p>
          Escolha uma rede. Deslize as ofertas ou abra o encarte em stories.
        </p>
      </div>
      <NetworkTabs
        networks={networks}
        value={network}
        onChange={(value) => {
          setNetwork(value);
          setMonth("");
          setWeek("");
        }}
        panelId={panelId}
      />
      <div className="flyer-tabs" aria-label="Edições dos encartes">
        {(Object.entries(categories) as [Category, string][]).map(
          ([key, label]) => (
            <button
              key={key}
              aria-pressed={category === key}
              onClick={() => {
                setCategory(key);
                setMonth("");
                setWeek("");
              }}
            >
              {label}
              <span aria-hidden="true">
                {
                  organized[key].filter(
                    (f) => !network || f.retailer_id === network,
                  ).length
                }
              </span>
            </button>
          ),
        )}
      </div>
      <div
        id={panelId}
        role="tabpanel"
        aria-label={
          network
            ? "Encartes de " + retailers.find((r) => r.id === network)?.name
            : "Encartes de todas as redes"
        }
      >
        {archived ? (
          <>
            <div className="filter-panel flyer-filters">
              <label>
                Mês
                <select
                  value={month}
                  onChange={(event) => {
                    setMonth(event.target.value);
                    setWeek("");
                  }}
                >
                  <option value="">Todos os meses</option>
                  {months.map((m) => (
                    <option key={m} value={m}>
                      {flyerMonthLabel(m)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Semana
                <select
                  value={week}
                  disabled={!month}
                  onChange={(event) => setWeek(event.target.value)}
                >
                  <option value="">
                    {month ? "Todas as semanas" : "Selecione um mês"}
                  </option>
                  {weeks.map((w) => (
                    <option key={w} value={w}>
                      {flyerWeekLabel(month, w)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="archive-note">
              Somente encartes com validade encerrada. Escolha o mês e depois a
              semana.
            </p>
          </>
        ) : (
          <p className="archive-note">
            {category === "current"
              ? "Todos os encartes ainda válidos aparecem aqui, mesmo quando há mais de um da mesma rede."
              : category === "future"
                ? "Estas ofertas ainda não começaram. Confira a data de início."
                : "A origem não informa um período completo. Confira antes de sair."}
          </p>
        )}
        <div className="flyer-grid">
          {shown.map((f) => (
            <FlyerCard key={f.id} f={f} flyers={shown} />
          ))}
        </div>
        {!shown.length && (
          <div className="empty compact">
            <BookOpen />
            <h3>Nenhum encarte neste filtro</h3>
            <p>
              {archived
                ? "Não há encartes vencidos para esta seleção. Escolha outro mês, semana ou rede."
                : "Escolha outra rede ou consulte os outros períodos."}
            </p>
          </div>
        )}
      </div>
      <p className="fineprint">
        Confira as condições e as lojas participantes no documento oficial. A
        validade não garante estoque em todas as lojas da rede.
      </p>
    </>
  );
}
