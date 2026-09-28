import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { IconButton } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

/** The entrance of the rail plays once per page load: never again on a filter, a radius or a return to Hoje. */
let railEntered = false;

/** A horizontally scrolling rail; `onEnd` is called when its last card comes into view (to load more). */
export function OfferRail({
  children,
  onEnd,
}: {
  children: ReactNode;
  onEnd?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [canPrevious, setCanPrevious] = useState(false),
    [canNext, setCanNext] = useState(false);
  const [entering, setEntering] = useState(() => !railEntered);
  useEffect(() => {
    if (!entering) return;
    railEntered = true;
    const timer = window.setTimeout(() => setEntering(false), 600);
    return () => window.clearTimeout(timer);
  }, [entering]);
  useEffect(() => {
    const node = ref.current!;
    const update = () => {
      setCanPrevious(node.scrollLeft > 2);
      setCanNext(node.scrollLeft + node.clientWidth < node.scrollWidth - 2);
    };
    update();
    const resize = new ResizeObserver(update);
    resize.observe(node);
    node.addEventListener("scroll", update, { passive: true });
    return () => {
      resize.disconnect();
      node.removeEventListener("scroll", update);
    };
  }, [children]);
  useEffect(() => {
    const node = ref.current!;
    const last = node.lastElementChild;
    if (!onEnd || !last) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onEnd();
      },
      { root: node, rootMargin: "0px 600px 0px 0px" },
    );
    observer.observe(last);
    return () => observer.disconnect();
  }, [children, onEnd]);
  function move(direction: number) {
    const node = ref.current!;
    const width =
      node.firstElementChild?.getBoundingClientRect().width || node.clientWidth;
    node.scrollBy({
      left: direction * (width + 12),
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }
  // Which edges have more cards behind them: the stylesheet fades only those (no system scrollbar).
  const edges = canPrevious && canNext ? "both" : canNext ? "end" : canPrevious ? "start" : "none";
  return (
    <section
      className="offer-rail"
      aria-label="Ofertas do dia"
      data-first-load={entering ? "" : undefined}
      data-edges={edges}
    >
      <div className="product-grid daily-grid" ref={ref}>
        {children}
      </div>
      {(canPrevious || canNext) && (
        <div className="offer-rail-navigation">
          <span>Deslize para ver mais ofertas</span>
          <Tooltip label="Anteriores">
            <IconButton label="Ofertas anteriores" disabled={!canPrevious} onClick={() => move(-1)}>
              <ChevronLeft size={18} aria-hidden="true" />
            </IconButton>
          </Tooltip>
          <Tooltip label="Próximas">
            <IconButton label="Próximas ofertas" disabled={!canNext} onClick={() => move(1)}>
              <ChevronRight size={18} aria-hidden="true" />
            </IconButton>
          </Tooltip>
        </div>
      )}
    </section>
  );
}
