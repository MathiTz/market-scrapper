import { useEffect, useState } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Past this many screens of scrolling the list has grown (infinite scroll) and the top is a long way up. */
const SHOW_AFTER_SCREENS = 2;

/**
 * A floating button that takes the page back to the top, shown once the person has scrolled well down.
 * `bottom` is its distance from the bottom of the screen in px, so it clears the mobile dock.
 */
export function BackToTop({ bottom }: { bottom: number }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const update = () => setVisible(window.scrollY > window.innerHeight * SHOW_AFTER_SCREENS);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  if (!visible) return null;
  return (
    <Button
      iconOnly
      className="back-to-top"
      style={{ bottom }}
      aria-label="Voltar ao topo"
      icon={<ArrowUp size={20} aria-hidden="true" />}
      onClick={() => {
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
        // The button disappears once the top is reached: leave keyboard focus at the start of the page, not nowhere.
        document.getElementById("conteudo")?.focus({ preventScroll: true });
      }}
    />
  );
}
