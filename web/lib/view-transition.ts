import { flushSync } from "react-dom";

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void> };
};

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Runs a React state update inside a same-document view transition when the browser has the API and the
 * person has not asked for less motion; anywhere else the update is plain and instant. `name` goes on
 * `<html data-vt>` for the duration, so the stylesheet can choose which elements morph (plan 006: only the
 * product photo that was tapped and the hero it becomes).
 */
export function withViewTransition(update: () => void, name?: string) {
  const doc = document as ViewTransitionDocument;
  if (!doc.startViewTransition || reducedMotion()) {
    update();
    return;
  }
  if (name) document.documentElement.dataset.vt = name;
  const transition = doc.startViewTransition(() => flushSync(update));
  transition.finished
    .catch(() => {}) // a transition superseded by a newer one rejects with InvalidStateError - expected, not a bug
    .finally(() => {
      if (name) delete document.documentElement.dataset.vt;
    });
}

/** Marks the photo of one product card as the origin of the next morph; any earlier mark is cleared. */
export function markHero(productId: string | null) {
  for (const marked of document.querySelectorAll("[data-hero]")) marked.removeAttribute("data-hero");
  if (!productId) return;
  document
    .querySelector(`[data-product-id~="${CSS.escape(productId)}"] .product-photo img`)
    ?.setAttribute("data-hero", "");
}
