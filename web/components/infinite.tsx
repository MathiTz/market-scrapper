import { useCallback, useEffect, useRef, useState } from "react";

/**
 * How many of `total` items to show: `step` to begin with, `step` more each time `more` is called,
 * starting over when `resetKey` changes (a new search or filter).
 */
export function useIncremental(total: number, step: number, resetKey: string) {
  const [state, setState] = useState({ key: resetKey, count: step });
  const count = Math.min(state.key === resetKey ? state.count : step, total);
  // Depends on `count` so each change gives the observer below a fresh callback and it checks again.
  const more = useCallback(
    () => setState({ key: resetKey, count: count + step }),
    [resetKey, count, step],
  );
  return { count, hasMore: count < total, more };
}

/** An invisible marker that calls `onVisible` when it scrolls near the viewport. */
export function LoadMore({ onVisible }: { onVisible: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onVisible();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [onVisible]);
  return <div ref={ref} className="load-more" aria-hidden="true" />;
}
