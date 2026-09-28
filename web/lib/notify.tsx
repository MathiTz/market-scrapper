import type { ReactNode } from "react";
import { toast, Toaster } from "sonner";
import { Check, Undo2, WifiOff } from "lucide-react";

type Options = { undo?: () => void; duration?: number; icon?: ReactNode };

/**
 * A short confirmation at the bottom of the screen (Sonner, headless: the look is `.toast` in
 * app/globals.css). Toasts stack, pause on hover, can be dragged away, and enter and leave through the same
 * edge. With `undo`, the toast stays longer and carries the way back; the list also keeps its own persistent
 * "Desfazer" notice, because a toast is never the only place for something that matters.
 */
export function notify(message: string, { undo, duration = 3200, icon }: Options = {}) {
  return toast.custom(
    (id) => (
      <div className="toast">
        {icon ?? <Check size={19} aria-hidden="true" />}
        <span>{message}</span>
        {undo && (
          <button
            type="button"
            className="toast-action"
            onClick={() => {
              undo();
              toast.dismiss(id);
            }}
          >
            <Undo2 size={16} aria-hidden="true" /> Desfazer
          </button>
        )}
      </div>
    ),
    { duration: undo ? 8000 : duration },
  );
}

export const notifyOffline = (message: string) =>
  notify(message, { icon: <WifiOff size={19} aria-hidden="true" /> });

/** The page's single toast stack: bottom centre, three at most, lifted above the mobile dock by `bottom`. */
export function Notifications({ bottom = 24 }: { bottom?: number }) {
  return (
    <Toaster
      position="bottom-center"
      offset={{ bottom }}
      mobileOffset={{ bottom }}
      gap={8}
      visibleToasts={3}
      toastOptions={{ unstyled: true, className: "toast-shell" }}
    />
  );
}
