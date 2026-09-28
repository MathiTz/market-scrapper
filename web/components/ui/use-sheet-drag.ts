import { useEffect, type RefObject } from "react";

/** Below this width the three dialogs are bottom sheets (app/globals.css, plan 008). */
const SHEET_QUERY = "(max-width: 760px)";
/** Pull past this share of the sheet's height, or flick faster than this (px/ms over the last ~100 ms), and it closes. */
const CLOSE_RATIO = 0.4;
const FLICK_VELOCITY = 0.5;
const VELOCITY_WINDOW_MS = 100;

/**
 * A damped spring from `from` to `to` that starts with the hand's own velocity (px/s), stepped by rAF.
 * Damping near the critical value (2·√stiffness ≈ 36) settles without a bounce; a little below it gives
 * the one small overshoot of a sheet snapping back. Returns a function that stops it (a new drag).
 */
function spring(
  from: number,
  to: number,
  velocity: number,
  damping: number,
  onUpdate: (value: number) => void,
  onComplete: () => void,
) {
  const stiffness = 320;
  let x = from;
  let v = velocity;
  let last = performance.now();
  let frame = 0;
  const step = (now: number) => {
    const dt = Math.min(0.064, (now - last) / 1000);
    last = now;
    v += (-stiffness * (x - to) - damping * v) * dt;
    x += v * dt;
    if (Math.abs(x - to) < 0.5 && Math.abs(v) < 20) {
      onUpdate(to);
      onComplete();
      return;
    }
    onUpdate(x);
    frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
  return () => cancelAnimationFrame(frame);
}

/**
 * Drag-to-dismiss for a dialog shown as a bottom sheet. The drag starts on the handle (the dialog's own
 * padding), on anything marked `data-sheet-grip` (the heading), never inside `data-scroll` (lists that
 * scroll), inputs or buttons. Pulling up meets friction; letting go springs back, or slides the sheet away
 * when it was pulled far or flicked. The spring carries the velocity of the hand, which CSS cannot do; with
 * reduced motion it is overdamped and short. No library: twenty lines of physics are lighter than any.
 */
export function useSheetDrag(ref: RefObject<HTMLDialogElement | null>, requestClose: (immediate?: boolean) => void) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !window.matchMedia(SHEET_QUERY).matches) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let pointerId = -1;
    let startY = 0;
    let y = 0;
    let dragging = false;
    let moved = false;
    let swallowClick = false;
    let stop: (() => void) | null = null;
    // The last few positions, to read the speed of the hand at the moment it lets go (not the average).
    let trail: { at: number; y: number }[] = [];
    const set = (value: number) => {
      y = value;
      el.style.transform = `translateY(${value}px)`;
    };
    const settle = (to: number, velocity: number, done?: () => void) => {
      const damping = reduced ? 48 : to === 0 ? 26 : 36;
      stop = spring(y, to, reduced ? 0 : velocity * 1000, damping, set, () => {
        stop = null;
        el.style.willChange = "";
        el.style.transition = "";
        if (done) done();
        else el.style.transform = "";
      });
    };
    const down = (event: PointerEvent) => {
      if (dragging || event.button !== 0 || !el.open) return;
      const target = event.target as HTMLElement;
      const onGrip = target === el || target.closest("[data-sheet-grip]") !== null;
      if (!onGrip && target.closest("[data-scroll], input, button, a, select, textarea, label") !== null) return;
      stop?.(); // a hand catching the sheet mid-spring takes over from where it is
      dragging = true;
      moved = false;
      pointerId = event.pointerId;
      startY = event.clientY;
      trail = [{ at: performance.now(), y: 0 }];
      el.setPointerCapture(event.pointerId);
      el.style.transition = "none";
      el.style.willChange = "transform";
    };
    const move = (event: PointerEvent) => {
      if (!dragging || event.pointerId !== pointerId) return;
      const dy = event.clientY - startY;
      moved = moved || Math.abs(dy) > 3;
      set(dy >= 0 ? dy : -Math.pow(-dy, 0.7)); // friction above the resting point
      trail.push({ at: performance.now(), y });
      if (trail.length > 10) trail.shift();
    };
    const up = (event: PointerEvent) => {
      if (!dragging || event.pointerId !== pointerId) return;
      dragging = false;
      if (!moved) {
        el.style.transition = "";
        el.style.willChange = "";
        return;
      }
      swallowClick = true; // the click that ends a drag must not count as a tap on the backdrop
      const now = performance.now();
      const from = trail.find((sample) => now - sample.at <= VELOCITY_WINDOW_MS) ?? trail[trail.length - 1];
      const velocity = now > from.at ? (y - from.y) / (now - from.at) : 0;
      if (y > el.offsetHeight * CLOSE_RATIO || velocity > FLICK_VELOCITY) {
        settle(el.offsetHeight, Math.max(velocity, 0), () => {
          requestClose(true); // already off screen: no exit transition to wait for
          el.style.transform = "";
        });
      } else settle(0, velocity);
    };
    const click = (event: MouseEvent) => {
      if (!swallowClick) return;
      swallowClick = false;
      event.stopPropagation();
      event.preventDefault();
    };
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("click", click, true);
    return () => {
      stop?.();
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      el.removeEventListener("click", click, true);
    };
  }, [ref, requestClose]);
}
