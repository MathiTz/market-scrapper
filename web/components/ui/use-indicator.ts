import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

/**
 * Measures the selected item inside a container and exposes its left edge and width as CSS variables
 * (`--x`, `--w`) for a single element that slides to it: the navigation pill, the dock marker, the
 * segmented control. Re-measured when `deps` change and when the container resizes.
 */
export function useIndicator<T extends HTMLElement>(selector: string, deps: readonly unknown[]) {
  const ref = useRef<T>(null);
  const [position, setPosition] = useState<{ x: number; w: number } | null>(null);
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const measure = () => {
      const selected = root.querySelector<HTMLElement>(selector);
      setPosition(selected ? { x: selected.offsetLeft, w: selected.offsetWidth } : null);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selector, ...deps]);
  return {
    ref,
    ready: position !== null,
    style: position ? ({ "--x": `${position.x}px`, "--w": `${position.w}px` } as CSSProperties) : undefined,
  };
}
