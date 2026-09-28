# 008 — Bottom sheet no mobile para "Perto de você", "Onde encontrar" e "Tamanhos", com arrasto e flick

- **Status**: DONE 28/09 (`components/ui/use-sheet-drag.ts`: alça = padding do próprio dialog, cabeçalho `data-sheet-grip`, corpo `data-scroll`; velocidade dos últimos 100 ms, > 0,5 px/ms fecha; `requestClose(true)` quando já saiu da tela. `motion` foi medido em 19 kB gzip para um único `animate` e removido: a mola é própria, vinte linhas em rAF, e parte da velocidade da mão)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: MEDIUM
- **Category**: Physicality & origin · Interruptibility
- **Estimated scope**: `package.json` (+`motion@13.4.4`), `components/ui/use-sheet-drag.ts` (novo), `components/ui/use-dialog.ts` (do plano 003), `components/nearby-filter.tsx`, `components/store-location.tsx`, `components/product-range-card.tsx`, `app/globals.css`

## Problem

No celular os três diálogos aparecem centrados (ou presos ao topo, no caso de "Perto de você"), com o polegar
longe dos controles e sem o gesto que qualquer app oferece: puxar para baixo para fechar.

```css
/* app/globals.css:659-671 — atual */
.nearby-dialog {
  --nearby-top: clamp(12px, 4dvh, 48px);
  width: min(540px, calc(100% - 24px));
  max-height: calc(100dvh - var(--nearby-top) - 12px);
  margin: var(--nearby-top) auto auto;
  …
}
```

## Target

Portão: ocasional → consistência espacial (vem de baixo, volta para baixo) e retorno ao gesto. Ferramenta:
CSS para abrir/fechar; `motion` (`animate` com spring) só para o arrasto, porque a pessoa pode reverter no
meio e a mola carrega a velocidade. Curva da sheet: `--ease-drawer` (iOS/Ionic), 500 ms; saída 400 ms.

```css
/* app/globals.css — alvo (só < 760 px) */
@media (max-width: 760px) {
  dialog[data-sheet] {
    position: fixed; inset: auto 0 0 0; margin: 0; width: 100%; max-width: none; max-height: calc(100dvh - 48px);
    border-radius: var(--md-radius-lg) var(--md-radius-lg) 0 0; padding-bottom: env(safe-area-inset-bottom);
    transform: translateY(100%); opacity: 1;
    transition: transform 400ms var(--ease-drawer), overlay 400ms allow-discrete, display 400ms allow-discrete;
    overscroll-behavior: contain; touch-action: none;
  }
  dialog[data-sheet][open]:not([data-closing]) { transform: translateY(0); transition-duration: var(--dur-sheet); @starting-style { transform: translateY(100%); } }
  dialog[data-sheet]::before { content: ""; display: block; width: 36px; height: 4px; margin: 8px auto 12px; border-radius: 2px; background: var(--md-border-strong); }
  .app-shell[data-sheet-open] > .main { transform: scale(0.96); border-radius: 12px; transition: transform var(--dur-sheet) var(--ease-drawer), border-radius var(--dur-sheet) var(--ease-drawer); transform-origin: top center; }
}
```

```ts
// components/ui/use-sheet-drag.ts — alvo
import { animate } from "motion";
export function useSheetDrag(ref: React.RefObject<HTMLDialogElement | null>, requestClose: () => void) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !window.matchMedia("(max-width: 760px)").matches) return;
    let startY = 0, startT = 0, dragging = false, y = 0;
    const set = (v: number) => { y = v; el.style.transform = `translateY(${v}px)`; };   // on the element, never via a CSS variable on a parent
    const down = (e: PointerEvent) => {
      if (dragging || e.button !== 0) return;                                              // multi-touch protection
      if ((e.target as HTMLElement).closest("input, button, a, select, textarea, [data-scroll]")) return;
      dragging = true; startY = e.clientY; startT = performance.now();
      el.setPointerCapture(e.pointerId); el.style.transition = "none"; el.style.willChange = "transform";
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const dy = e.clientY - startY;
      set(dy >= 0 ? dy : -Math.pow(-dy, 0.7));                                             // friction above the resting point
    };
    const up = () => {
      if (!dragging) return;
      dragging = false; el.style.willChange = "";
      const velocity = y / (performance.now() - startT);                                   // px per ms
      if (y > el.offsetHeight * 0.4 || velocity > 0.11) {                                  // distance OR flick
        animate(y, el.offsetHeight, { type: "spring", duration: 0.5, bounce: 0, onUpdate: set, onComplete: () => { el.style.transform = ""; el.style.transition = ""; requestClose(); } });
      } else {
        animate(y, 0, { type: "spring", duration: 0.5, bounce: 0.2, onUpdate: set, onComplete: () => { el.style.transform = ""; el.style.transition = ""; } });
      }
    };
    el.addEventListener("pointerdown", down); el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
    return () => { el.removeEventListener("pointerdown", down); el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up); };
  }, [ref, requestClose]);
}
```

O conteúdo rolável interno recebe `data-scroll` (a lista de sugestões, a lista de tamanhos), para o arrasto
só começar na alça e no cabeçalho; dentro da área `data-scroll` o gesto é rolagem normal.

## Repo conventions to follow

- Os diálogos passam pelo hook `useDialog` do plano 003 (`requestClose` cuida da saída e do foco).
- `env(safe-area-inset-bottom)` já é usado no dock; a sheet usa o mesmo.
- `motion` importado de `"motion"` (a função `animate` avulsa, sem o runtime React, ~5 kB gz); não usar
  `motion/react` aqui.

## Steps

1. `npm install motion@13.4.4` (cache isolado).
2. Criar `components/ui/use-sheet-drag.ts` conforme o alvo.
3. Adicionar `data-sheet` aos três `<dialog>` (nearby, location, range) e marcar as áreas roláveis com
   `data-scroll`; chamar `useSheetDrag(ref, requestClose)` em cada um.
4. Em `Market`, colocar `data-sheet-open` no `.app-shell` enquanto qualquer sheet está aberta (o hook
   `useDialog` pode expor `isOpen`; ou usar `document.querySelector("dialog[data-sheet][open]")` num
   `MutationObserver` simples).
5. CSS do alvo; no desktop nada muda (regras dentro de `max-width: 760px`).
6. Reduced motion: `--dur-sheet` já cai para 200 ms (plano 002); no hook, se `prefers-reduced-motion`,
   substituir as molas por `duration: 0.2, ease: "easeOut"` e não escalar o fundo.

## Boundaries

- Não usar `vaul` nem `motion/react` (drag do Motion) para manter o `<dialog>` nativo e o bundle pequeno.
- Não mudar o comportamento no desktop.
- Não bloquear a rolagem interna das listas (`data-scroll`).

## Verification

- **Mechanical**: `npm run typecheck && npm test && npm run build` (bundle ≤ +8 kB gz); fluxos "GPS negado" e
  "Esc fecha e devolve o foco" seguem passando a 390 px.
- **Feel check** (em aparelho real, não só no emulador): abrir "Perto de você": a sheet sobe em 500 ms e o
  fundo recua a 96%; arrastar devagar e soltar antes de 40%: volta com uma mola leve; dar um flick curto para
  baixo: fecha mesmo sem chegar a 40%; puxar para cima: resiste (atrito), não trava; arrastar dentro da lista
  de sugestões rola a lista, não a sheet; teclado virtual aberto no campo de endereço não cobre o botão
  "Buscar endereço" (a sheet respeita `100dvh`).
- **Done when**: os três diálogos são sheets abaixo de 760 px e diálogos centrados acima, com o mesmo código
  de conteúdo.
