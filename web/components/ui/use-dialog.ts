import { useCallback, useEffect, useRef, type RefObject } from "react";

/** Longer than the longest exit transition (a sheet, 400 ms): the dialog closes even where transitions never end. */
const EXIT_FALLBACK_MS = 460;

/**
 * Opens a native <dialog> as a modal while `open` is true, and closes it only after its exit transition
 * (`dialog[data-closing]` in app/globals.css) has ended, handing focus back to the opener. Escape, the ×
 * and a click on the backdrop all go through `requestClose`, so every way out looks the same. A dialog
 * marked `data-sheet` also flags the document (`html[data-sheet-open]`) so the page can recede on phones.
 */
export function useDialog(open: boolean, onClosed: () => void, opener?: RefObject<HTMLElement | null>) {
  const ref = useRef<HTMLDialogElement>(null);
  const closed = useRef(onClosed);
  closed.current = onClosed;
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (!dialog.open) dialog.showModal();
    if (dialog.dataset.sheet !== undefined) document.documentElement.dataset.sheetOpen = "";
    return () => {
      document.body.style.overflow = overflow;
      delete document.documentElement.dataset.sheetOpen;
      // Unmounted while still open (a parent going away, StrictMode's rehearsal): no transition to wait for.
      if (dialog.open) dialog.close();
    };
  }, [open]);
  /** Closes after the exit transition; `immediate` when the dialog is already off screen (a dragged sheet). */
  const requestClose = useCallback(
    (immediate = false) => {
      const dialog = ref.current;
      if (!dialog || !dialog.open || dialog.dataset.closing !== undefined) return;
      dialog.dataset.closing = "";
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        dialog.removeEventListener("transitionend", onEnd);
        delete dialog.dataset.closing;
        dialog.close();
        const target = opener?.current;
        if (target?.isConnected) target.focus({ preventScroll: true });
        closed.current();
      };
      const onEnd = (event: TransitionEvent) => {
        if (event.target === dialog) finish();
      };
      if (immediate) {
        finish();
        return;
      }
      dialog.addEventListener("transitionend", onEnd);
      window.setTimeout(finish, EXIT_FALLBACK_MS);
    },
    [opener],
  );
  return { ref, requestClose };
}
