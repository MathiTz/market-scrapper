import { useEffect, useRef, useState, type RefObject } from "react";
import {
  BookOpen,
  ArrowUpRight,
  Download,
  Share2,
  ZoomIn,
  ZoomOut,
  X,
  Maximize2,
} from "lucide-react";
import { flyerState, type Flyer } from "@/lib/domain";
import {
  flyerPages,
  flyerDateRange,
  flyerStates,
  flyerShareUrl,
} from "@/lib/flyers";
import {
  FlyerValidity,
  NetworkTabs,
  PageControls,
  PageProgress,
  useFlyerPlayer,
} from "./flyer-player";

/** The flyer viewer zooms from 25% to 150% of the size that fits the screen, in 25% steps. */
const MIN_ZOOM = 25;
const MAX_ZOOM = 150;
const ZOOM_STEP = 25;

export function FlyerDialog({
  f,
  flyers = [f],
  initialPage = 0,
  onClose,
  opener,
}: {
  f: Flyer;
  flyers?: Flyer[];
  initialPage?: number;
  onClose: () => void;
  opener: RefObject<HTMLButtonElement | null>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [network, setNetwork] = useState(f.retailer_id);
  // Keep the reading sequence stable if another edition expires while this dialog is open.
  const [editions] = useState(() => [...flyers]);
  const networks = [
    ...new Map(
      editions.map((flyer) => [
        flyer.retailer_id,
        {
          id: flyer.retailer_id,
          name: flyer.retailer_name || flyer.retailer_id,
          count: editions.filter((item) => item.retailer_id === flyer.retailer_id)
            .length,
        },
      ]),
    ).values(),
  ];
  useEffect(() => {
    const dialog = ref.current!,
      overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (opener.current?.isConnected) opener.current.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="flyer-dialog"
      aria-labelledby="flyer-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="story-topbar">
        <span>Encartes em stories</span>
        <button
          className="icon-button"
          aria-label="Fechar encarte"
          onClick={onClose}
          autoFocus
        >
          <X size={22} />
        </button>
      </div>
      <NetworkTabs
        networks={networks}
        value={network}
        onChange={setNetwork}
        panelId="flyer-story-content"
        label="Redes nos stories"
      />
      <StoryReader
        key={network}
        flyers={editions.filter((item) => item.retailer_id === network)}
        initialFlyer={f.id}
        initialPage={initialPage}
      />
    </dialog>
  );
}

function StoryReader({
  flyers,
  initialFlyer,
  initialPage,
}: {
  flyers: Flyer[];
  initialFlyer: string;
  initialPage: number;
}) {
  const frames = flyers.flatMap((flyer) => {
    const pages = flyerPages(flyer);
    return (pages.length ? pages : [{ url: "", type: "image" as const }]).map(
      (page, pageIndex) => ({ ...page, flyer, pageIndex, total: pages.length }),
    );
  });
  const start = Math.max(
    0,
    frames.findIndex(
      (frame) =>
        frame.flyer.id === initialFlyer && frame.pageIndex === initialPage,
    ),
  );
  const [zoom, setZoom] = useState(100);
  // 100% is the page fitted to the screen; the image is sized from its own dimensions and the viewport.
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [loaded, setLoaded] = useState("");
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [shareLink, setShareLink] = useState("");
  const [held, setHeld] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(start);
  const ready = frames[activeIndex]?.url === loaded && !!loaded;
  const player = useFlyerPlayer(
    frames.length,
    !ready || zoom > 100 || busy || held,
    start,
  );
  const frame = frames[player.index],
    f = frame.flyer,
    demo = f.method === "demo";
  const isFailed = !!frame.url && failed === frame.url;
  const downloadUrl = f.media_type === "pdf" ? f.media_url : frame.url;
  useEffect(() => {
    setActiveIndex(player.index);
    setZoom(100);
    setNatural(null);
    setStatus("");
    setShareLink("");
    viewport.current?.scrollTo(0, 0);
  }, [player.index]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const update = () => setBox({ w: node.clientWidth, h: node.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const fit =
    natural && box.w && box.h
      ? Math.min(box.w / natural.w, box.h / natural.h)
      : null;

  async function download() {
    if (!downloadUrl) return;
    player.pause();
    const fileUrl = new URL(downloadUrl, window.location.href);
    if (fileUrl.origin !== window.location.origin) {
      // Official hosts may forbid cross-origin fetch. Let the browser save the original directly.
      window.open(fileUrl.href, "_blank", "noopener,noreferrer");
      setStatus("Use a opção de salvar do navegador na aba do arquivo original.");
      return;
    }
    setBusy(true);
    setStatus("");
    const abort = new AbortController();
    controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch(downloadUrl, {
        credentials: "omit",
        referrerPolicy: "no-referrer",
        signal: abort.signal,
      });
      if (!response.ok) throw Error("Arquivo indisponível");
      const blob = await response.blob();
      if (!/^(image\/|application\/pdf)/i.test(blob.type))
        throw Error("Formato inesperado");
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      const extension = blob.type.includes("pdf")
        ? "pdf"
        : blob.type.includes("svg")
          ? "svg"
          : blob.type.split("/")[1].split(";")[0];
      link.download =
        f.id +
        (frame.pageIndex && f.media_type !== "pdf"
          ? "-p" + (frame.pageIndex + 1)
          : "") +
        "." +
        extension;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("Download iniciado.");
    } catch {
      setStatus(
        "Não foi possível baixar aqui. Abra o arquivo original e use a opção de salvar do seu navegador.",
      );
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
    }
  }
  async function share() {
    player.pause();
    const url = flyerShareUrl(
      { ...f, media_url: frame.url || f.media_url },
      window.location.origin,
    );
    setStatus("");
    if (navigator.share) {
      try {
        await navigator.share({
          title:
            (demo ? "Encarte fictício" : "Encarte") + " · " + f.retailer_name,
          text:
            f.title +
            " · " +
            flyerDateRange(f) +
            " · página " +
            (frame.pageIndex + 1),
          url,
        });
        return;
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setStatus("Link copiado para compartilhar.");
    } catch {
      setShareLink(url);
      setStatus("Copie o link abaixo para compartilhar.");
    }
  }

  return (
    <div
      id="flyer-story-content"
      className="flyer-story-content"
      role="tabpanel"
      aria-label={"Encartes de " + f.retailer_name}
    >
      <div className="flyer-dialog-heading">
        <div>
          <p>
            {f.retailer_name} · {demo ? "Encarte fictício" : "Encarte oficial"}{" "}
            · Página {frame.pageIndex + 1} de {Math.max(1, frame.total)}
          </p>
          <h2 id="flyer-dialog-title">{f.title}</h2>
          <p>
            {flyerDateRange(f)} · <strong>{flyerStates[flyerState(f)]}</strong>
          </p>
        </div>
        <FlyerValidity flyer={f} />
      </div>
      <div className="story-playback">
        <PageProgress player={player} count={frames.length} />
        <PageControls player={player} count={frames.length} />
      </div>
      <div className="flyer-toolbar" onFocusCapture={() => player.pause()}>
        {frame.type === "image" && frame.url && !isFailed && (
          <div className="flyer-zoom" aria-label="Ampliação do encarte">
            <button
              className="icon-button"
              aria-label="Reduzir encarte"
              disabled={zoom <= MIN_ZOOM}
              onClick={() => setZoom((z) => Math.max(MIN_ZOOM, z - ZOOM_STEP))}
            >
              <ZoomOut size={20} />
            </button>
            <span aria-live="polite">{zoom}%</span>
            <button
              className="icon-button"
              aria-label="Ampliar encarte"
              disabled={zoom >= MAX_ZOOM}
              onClick={() => {
                player.pause();
                setZoom((z) => Math.min(MAX_ZOOM, z + ZOOM_STEP));
              }}
            >
              <ZoomIn size={20} />
            </button>
            <button
              className="icon-button"
              aria-label="Ajustar à tela"
              onClick={() => setZoom(100)}
            >
              <Maximize2 size={19} />
            </button>
          </div>
        )}
        <button
          className="secondary"
          aria-label="Baixar encarte"
          disabled={!downloadUrl || busy}
          onClick={download}
        >
          <Download size={18} />
          {busy
            ? "Baixando…"
            : f.media_type === "pdf"
              ? "Baixar PDF"
              : "Baixar"}
        </button>
        <button
          className="secondary"
          aria-label="Compartilhar encarte"
          onClick={share}
        >
          <Share2 size={18} />
          Compartilhar
        </button>
      </div>
      <div
        ref={viewport}
        className={`flyer-viewport${frame.url && !isFailed && frame.type !== "pdf" ? " image-view" : ""}`}
        style={{
          touchAction:
            zoom > 100 ? "pan-x pan-y pinch-zoom" : "pan-y pinch-zoom",
        }}
        tabIndex={0}
        aria-label="Documento do encarte"
        onKeyDown={(event) => {
          if (zoom > 100) return;
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            player.go(player.index + (event.key === "ArrowRight" ? 1 : -1));
          }
        }}
        onPointerDown={(event) => {
          if (
            event.button !== 0 ||
            zoom > 100 ||
            (event.target as HTMLElement).closest("a,button,object")
          )
            return;
          touch.current = { x: event.clientX, y: event.clientY };
          setHeld(true);
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerUp={(event) => {
          setHeld(false);
          const origin = touch.current;
          touch.current = null;
          if (
            zoom <= 100 &&
            origin &&
            Math.abs(event.clientX - origin.x) > 45 &&
            Math.abs(event.clientY - origin.y) < 60
          )
            player.go(player.index + (event.clientX < origin.x ? 1 : -1));
        }}
        onPointerCancel={() => {
          setHeld(false);
          touch.current = null;
        }}
      >
        {frame.url && !isFailed ? (
          frame.type === "pdf" ? (
            <object
              data={frame.url}
              type="application/pdf"
              aria-label={"PDF " + f.title}
              onLoad={() => setLoaded(frame.url)}
            >
              <p>Abra o arquivo original para visualizar este PDF.</p>
            </object>
          ) : (
            <img
              key={frame.url}
              className="flyer-image"
              src={frame.url}
              alt={
                "Encarte " +
                f.title +
                " de " +
                f.retailer_name +
                (demo ? " · dados fictícios" : "") +
                " · página " +
                (frame.pageIndex + 1)
              }
              style={
                fit && natural
                  ? { width: Math.round((natural.w * fit * zoom) / 100), height: "auto" }
                  : { width: "100%", height: "100%" }
              }
              draggable={false}
              referrerPolicy="no-referrer"
              onLoad={(event) => {
                setNatural({
                  w: event.currentTarget.naturalWidth,
                  h: event.currentTarget.naturalHeight,
                });
                setLoaded(frame.url);
                setFailed("");
              }}
              onError={() => {
                setFailed(frame.url);
                player.pause();
              }}
            />
          )
        ) : (
          <div className="empty compact">
            <BookOpen size={36} />
            <h3>
              {isFailed
                ? "Não foi possível carregar o arquivo"
                : "Arquivo ainda não cadastrado"}
            </h3>
            <p>
              {isFailed
                ? "Consulte o documento diretamente na origem."
                : "Temos o link da página oficial. A imagem ou o PDF para ampliar e baixar ainda não foi cadastrado."}
            </p>
            <a
              className="secondary"
              href={f.source_url}
              target="_blank"
              rel="noreferrer"
            >
              Abrir no site oficial <ArrowUpRight size={18} />
            </a>
          </div>
        )}
      </div>
      <div className="flyer-dialog-footer">
        {frame.url && (
          <a
            className="text-link"
            href={frame.url}
            target="_blank"
            rel="noreferrer"
          >
            Abrir arquivo {demo ? "demonstrativo" : "original"}{" "}
            <ArrowUpRight size={16} />
          </a>
        )}
        {frame.type === "pdf" && (
          <p className="small">
            Se o PDF não aparecer, abra o arquivo original.
          </p>
        )}
        <p className="small">{f.scope}</p>
        {!demo && frame.url && (
          <a
            className="text-link"
            href={f.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Origem: site oficial <ArrowUpRight size={16} />
          </a>
        )}
        <p className="flyer-status" role="status">
          {status}
        </p>
        {shareLink && (
          <label className="share-link">
            Link para compartilhar
            <input
              readOnly
              value={shareLink}
              onFocus={(event) => event.target.select()}
            />
          </label>
        )}
      </div>
    </div>
  );
}
