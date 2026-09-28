import { useCallback, useState, type ReactElement, type ReactNode } from "react";
import { Tooltip as BaseTooltip } from "@base-ui-components/react/tooltip";

/** One provider per page: the first tooltip waits 400 ms, its neighbours open at once while the group is warm. */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <BaseTooltip.Provider delay={400} closeDelay={0} timeout={400}>
      {children}
    </BaseTooltip.Provider>
  );
}

/**
 * The visible name of an icon-only control (previous, next, close, share, remove). The child keeps its
 * aria-label: the tooltip is a complement for sighted people, never the accessible name. Inside a native
 * <dialog> the popup is portalled into the dialog itself, so the top layer does not hide it. Prices,
 * conditions and distances never go in a tooltip (they must be readable without a pointer).
 */
export function Tooltip({
  label,
  side = "top",
  children,
}: {
  label: string;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactElement<Record<string, unknown>>;
}) {
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const triggerRef = useCallback((element: HTMLElement | null) => {
    const dialog = element?.closest("dialog") ?? null;
    setContainer((current) => (current === dialog ? current : dialog));
  }, []);
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger ref={triggerRef} render={children} />
      <BaseTooltip.Portal container={container ?? undefined}>
        <BaseTooltip.Positioner side={side} sideOffset={6} className="tooltip-positioner">
          <BaseTooltip.Popup className="tooltip-popup">{label}</BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}
