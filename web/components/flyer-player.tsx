import { useEffect, useReducer, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, Timer } from "lucide-react";
import { flyerCountdown } from "@/lib/flyers";
import type { Flyer } from "@/lib/domain";

export const PAGE_DURATION = 8000;
type Playback = { index: number; elapsed: number; playing: boolean };
type Action =
  | { type: "play"; playing: boolean }
  | { type: "go"; index: number }
  | { type: "tick"; delta: number; count: number; loop: boolean };
function reduce(state: Playback, action: Action): Playback {
  if (action.type === "play") return { ...state, playing: action.playing };
  if (action.type === "go")
    return { index: action.index, elapsed: 0, playing: false };
  const elapsed = state.elapsed + action.delta;
  if (elapsed < PAGE_DURATION) return { ...state, elapsed };
  if (state.index + 1 < action.count)
    return { ...state, index: state.index + 1, elapsed: 0 };
  return action.loop
    ? { ...state, index: 0, elapsed: 0 }
    : { ...state, elapsed: PAGE_DURATION, playing: false };
}

export function useFlyerPlayer(
  count: number,
  suspended = false,
  initial = 0,
  loop = false,
) {
  const [state, dispatch] = useReducer(reduce, {
    index: initial,
    elapsed: 0,
    playing: false,
  });
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    dispatch({ type: "play", playing: !media.matches });
    const change = () => {
      if (media.matches) dispatch({ type: "play", playing: false });
    };
    const visibility = () => setHidden(document.hidden);
    visibility();
    media.addEventListener("change", change);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      media.removeEventListener("change", change);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  const playing = state.playing && !suspended && !hidden && count > 1;
  useEffect(() => {
    if (!playing) return;
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const current = performance.now();
      dispatch({
        type: "tick",
        delta: Math.min(current - previous, 250),
        count,
        loop,
      });
      previous = current;
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing, count, loop]);
  return {
    ...state,
    playing,
    go: (index: number) =>
      dispatch({ type: "go", index: Math.max(0, Math.min(count - 1, index)) }),
    pause: () => dispatch({ type: "play", playing: false }),
    toggle: () => {
      if (!state.playing && state.elapsed >= PAGE_DURATION)
        dispatch({ type: "go", index: 0 });
      dispatch({ type: "play", playing: !state.playing });
    },
  };
}

export type FlyerPlayer = ReturnType<typeof useFlyerPlayer>;
export function PageProgress({
  player,
  count,
}: {
  player: FlyerPlayer;
  count: number;
}) {
  return (
    <div className="story-progress" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <span key={index}>
          <i
            style={{
              width: `${index < player.index ? 100 : index === player.index ? (player.elapsed / PAGE_DURATION) * 100 : 0}%`,
            }}
          />
        </span>
      ))}
    </div>
  );
}

export function PageControls({
  player,
  count,
}: {
  player: FlyerPlayer;
  count: number;
}) {
  if (count <= 1) return null;
  return (
    <div className="story-controls" aria-label="Navegação das páginas">
      <button
        className="icon-button"
        aria-label="Página anterior"
        disabled={player.index === 0}
        onClick={() => player.go(player.index - 1)}
      >
        <ChevronLeft size={20} />
      </button>
      <span className="story-page-count" aria-live="off">
        {player.index + 1} / {count}
      </span>
      <button
        className="icon-button"
        aria-label="Próxima página"
        disabled={player.index >= count - 1}
        onClick={() => player.go(player.index + 1)}
      >
        <ChevronRight size={20} />
      </button>
      <span className="story-timer" aria-live="off">
        {player.playing
          ? `Próxima em ${Math.ceil((PAGE_DURATION - player.elapsed) / 1000)}s`
          : "Pausado"}
      </span>
      <button
        className="icon-button story-play"
        aria-label={player.playing ? "Pausar páginas" : "Reproduzir páginas"}
        onClick={player.toggle}
      >
        {player.playing ? <Pause size={18} /> : <Play size={18} />}
      </button>
    </div>
  );
}

export function FlyerValidity({ flyer }: { flyer: Flyer }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span className="flyer-validity">
      <Timer size={14} aria-hidden="true" />
      {now ? flyerCountdown(flyer, now) : "Conferindo validade…"}
    </span>
  );
}

export function useInView() {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { threshold: 0.15 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, visible };
}

export function NetworkTabs({
  networks,
  value,
  onChange,
  label = "Redes dos encartes",
  panelId,
}: {
  networks: { id: string; name: string; count: number }[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
  panelId: string;
}) {
  return (
    <div className="flyer-networks" role="tablist" aria-label={label}>
      {networks.map((network, index) => (
        <button
          key={network.id}
          type="button"
          role="tab"
          aria-selected={value === network.id}
          aria-controls={panelId}
          tabIndex={value === network.id ? 0 : -1}
          onClick={() => onChange(network.id)}
          onKeyDown={(event) => {
            let next = index;
            if (event.key === "ArrowRight")
              next = (index + 1) % networks.length;
            else if (event.key === "ArrowLeft")
              next = (index + networks.length - 1) % networks.length;
            else if (event.key === "Home") next = 0;
            else if (event.key === "End") next = networks.length - 1;
            else return;
            event.preventDefault();
            onChange(networks[next].id);
            (
              event.currentTarget.parentElement?.children[
                next
              ] as HTMLButtonElement
            )?.focus();
          }}
        >
          <span className="network-avatar" aria-hidden="true">
            {network.id
              ? network.name
                  .split(/\s+/)
                  .filter((word) => !["de", "do", "da"].includes(word))
                  .map((word) => word[0])
                  .slice(0, 2)
                  .join("")
              : "•"}
          </span>
          <span>
            {network.name}
            <small>
              {network.count} {network.count === 1 ? "encarte" : "encartes"}
            </small>
          </span>
        </button>
      ))}
    </div>
  );
}
