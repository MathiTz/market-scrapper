import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

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
  return (
    <section className="offer-rail" aria-label="Ofertas do dia">
      <div className="product-grid daily-grid" ref={ref}>
        {children}
      </div>
      {(canPrevious || canNext) && (
        <div className="offer-rail-navigation">
          <span>Deslize para ver mais ofertas</span>
          <button
            className="icon-button"
            aria-label="Ofertas anteriores"
            disabled={!canPrevious}
            onClick={() => move(-1)}
          >
            <ChevronLeft size={18} />
          </button>
          <button
            className="icon-button"
            aria-label="Próximas ofertas"
            disabled={!canNext}
            onClick={() => move(1)}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </section>
  );
}
