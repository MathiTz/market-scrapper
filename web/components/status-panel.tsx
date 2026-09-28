import type { ReactNode } from "react";
import { Inbox, RefreshCw, TriangleAlert, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * A view-level state that replaces content which cannot be shown right now: the service failed, the device
 * is offline or there is really nothing to show. Each says what happened, what still works and how to go on,
 * so a failure is never read as "there are no offers".
 */
export function StatusPanel({
  kind,
  title,
  children,
  actions,
}: {
  kind: "error" | "offline" | "empty";
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const Icon = kind === "error" ? TriangleAlert : kind === "offline" ? WifiOff : Inbox;
  return (
    <div className={`empty compact status-panel status-${kind}`}>
      <Icon size={30} aria-hidden="true" />
      <h3>{title}</h3>
      {children}
      {actions && <div className="status-actions">{actions}</div>}
    </div>
  );
}

/** The retry button used by the error states: asks for the snapshot again without reloading the page. */
export function RetryButton({ onRetry, busy }: { onRetry: () => void; busy: boolean }) {
  return (
    <Button variant="primary" onClick={onRetry} loading={busy} icon={<RefreshCw size={17} aria-hidden="true" />}>
      {busy ? "Tentando…" : "Tentar novamente"}
    </Button>
  );
}
