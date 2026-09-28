# 006 — View Transitions: a foto do cartão vira o herói do produto; abas com pílula que desliza; faixa Hoje

- **Status**: DONE 28/09 (`lib/view-transition.ts` + `markHero`; `components/ui/use-indicator.ts` para a pílula e o marcador do dock; a faixa entra uma vez por carga de página e desvanece só nas bordas com mais cartões)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: MEDIUM
- **Category**: Missed opportunities · Cohesion & tokens
- **Estimated scope**: `lib/view-transition.ts` (novo), `components/market.tsx` (`openProduct`, `closeProduct`, `navigate`, nav desktop e dock), `components/product-card.tsx`, `components/offer-rail.tsx`, `app/globals.css`

## Problem

Abrir um produto troca o DOM e rola ao topo; voltar restaura a rolagem, mas sem nenhuma continuidade
visual. Trocar de aba é uma troca de classe. A faixa Hoje aparece inteira de uma vez e mostra a barra de
rolagem do sistema.

```tsx
// components/market.tsx:334-344 — atual
const openProduct = (product: Product) => {
  if (!active) returnTo.current = { scroll: window.scrollY, productId: product.id };
  setSharedNotice("");
  window.history.pushState({ mdProduct: product.id }, "", `${basePath}?${new URLSearchParams({ produto: product.id })}`);
  setActive(product);
  window.scrollTo({ top: 0, behavior: "instant" });
};
```

```css
/* app/globals.css:151-154 — atual */
.desktop-nav button.selected {
  background: #e3ede6;
  color: var(--green);
}
/* app/globals.css:3041 — atual (barra de rolagem visível, sem máscara) */
.offer-rail .daily-grid { …; scrollbar-width: thin; scrollbar-color: #a5bdaf transparent; … }
```

## Target

Portões: abrir produto (ocasional) → **consistência espacial**, o momento-assinatura; trocar aba (~10/dia)
→ indicação de estado, curto e sem deslocamento; faixa (primeira carga) → delight raro, 240 ms no total.
Ferramenta: View Transitions API (nativa; sem suporte = instantâneo), CSS e `el.animate()`.

```ts
// lib/view-transition.ts — alvo
import { flushSync } from "react-dom";
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
/** Runs a React state update inside a same-document view transition when the browser supports it. */
export function withViewTransition(update: () => void, name?: string) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } };
  if (!doc.startViewTransition || reduced()) return update();
  if (name) document.documentElement.dataset.vt = name;
  const transition = doc.startViewTransition(() => flushSync(update));
  transition.finished.finally(() => { delete document.documentElement.dataset.vt; });
}
```

```css
/* app/globals.css — alvo */
::view-transition-old(root), ::view-transition-new(root) { animation-duration: 150ms; animation-timing-function: var(--ease-out); }
html[data-vt="product"] .product-photo img[data-hero], .product-hero img { view-transition-name: product-photo; }
::view-transition-group(product-photo) { animation-duration: var(--dur-modal); animation-timing-function: var(--ease-out); }
::view-transition-old(product-photo) { animation: none; opacity: 0; }   /* the new image morphs alone: no double exposure */
/* nav pill (desktop) */
.desktop-nav { position: relative; }
.desktop-nav .nav-pill { position: absolute; inset-block: 0; left: 0; width: 0; border-radius: var(--md-radius-pill); background: var(--md-selected-fill);
  transform: translateX(var(--x, 0px)); width: var(--w, 0px); transition: transform var(--dur-menu) var(--ease-in-out), width var(--dur-menu) var(--ease-in-out); pointer-events: none; }
.desktop-nav button { position: relative; z-index: 1; background: transparent; }
.desktop-nav button.selected { color: var(--md-selected-text); }
/* rail */
.offer-rail .daily-grid { scrollbar-width: none; mask-image: linear-gradient(to right, transparent, black 20px, black calc(100% - 20px), transparent); }
.offer-rail .daily-grid::-webkit-scrollbar { display: none; }
.offer-rail[data-first-load] .product-card { animation: rail-in 300ms var(--ease-out) both; animation-delay: calc(var(--i) * 40ms); }
@keyframes rail-in { from { opacity: 0; transform: translateY(var(--motion-lift)); } }
```

```tsx
// components/market.tsx — alvo
const openProduct = (product: Product) => {
  …
  document.querySelector(`[data-product-id~="${CSS.escape(product.id)}"] .product-photo img`)?.setAttribute("data-hero", "");
  withViewTransition(() => setActive(product), "product");
  window.scrollTo({ top: 0, behavior: "instant" });
};
// closeProduct / popstate: withViewTransition(() => setActive(null), "product") (o herói volta ao cartão restaurado)
// navigate: withViewTransition(() => { …setView(v)… })  (crossfade de 150 ms, sem nome: só root)
// nav desktop: um <span className="nav-pill" style={{ "--x": `${left}px`, "--w": `${width}px` }} /> medido com
// getBoundingClientRect do botão selecionado num useLayoutEffect (recalcular em resize).
// OfferRail: data-first-load enquanto o rail nunca recebeu dados; cada ProductCard recebe style={{ "--i": Math.min(index, 5) }};
// remover o atributo após 400 ms (setTimeout) e nunca reaplicar em filtros.
```

## Repo conventions to follow

- Estado da vista vive em `Market` (`market.tsx`); o histórico do produto já usa `pushState` /
  `popstate`; a transição envolve o `setState`, não substitui a lógica.
- Os cartões já têm `data-product-id` (usado para devolver o foco); reaproveitar para achar a foto.
- `useLayoutEffect` já é usado para restaurar rolagem; a medição da pílula segue o mesmo padrão.

## Steps

1. Criar `lib/view-transition.ts`.
2. `market.tsx`: envolver `setActive(product)` em `openProduct`, `setActive(null)` em `closeProduct` e no
   `popstate`, e o bloco de `navigate` com `withViewTransition`; marcar a foto clicada com `data-hero` antes
   de abrir e remover a marca ao fechar (a restauração de foco já localiza o cartão).
3. `product-card.tsx`: nada além de aceitar `style` para `--i` (faixa).
4. Nav desktop: adicionar o `nav-pill` e a medição; dock mobile: o indicador de 3 px existente
   (`.bottom-nav button.selected:before`) vira um único elemento deslizante com o mesmo mecanismo.
5. `offer-rail.tsx`: `data-first-load`, índice por cartão, máscara e barra oculta (CSS do alvo); as setas
   já usam `scrollBy` suave com respeito a reduced motion.
6. CSS do alvo; garantir `view-transition-name` único por vez (só a foto marcada e o herói).

## Boundaries

- Não usar `view-transition-name` por produto em todos os cartões (custo de snapshot); só no clicado.
- Não animar a troca de aba com deslocamento lateral ("direction-aware"): crossfade apenas.
- Não animar a faixa após filtros, busca ou troca de raio.
- Não instalar `motion` neste plano.

## Verification

- **Mechanical**: `npm run typecheck && npm test`; fluxos "voltar do navegador fecha o produto" e "foco no
  título" continuam passando; no Firefox sem suporte a View Transitions o comportamento é o atual.
- **Feel check**: no Chrome, clicar num cartão: a foto cresce até o herói do detalhe enquanto o resto faz
  crossfade (250 ms); voltar: a foto retorna ao cartão. Abrir DevTools > Animations a 10% e confirmar que a
  imagem antiga não aparece por cima da nova. Trocar de aba: a pílula desliza 180 ms e o conteúdo faz
  crossfade sem se mover. Primeira carga da Hoje: cartões entram um a um (40 ms), nunca de novo ao filtrar.
- **Done when**: `document.startViewTransition` é chamado só em abrir/fechar produto e trocar de vista; a
  barra de rolagem da faixa não aparece com ponteiro fino e a máscara desvanece as bordas.
