# 002 — Tokens de motion, política de reduced motion e retorno ao pressionar

- **Status**: DONE 27/09 (tokens de motion em `tokens.css`; reduced motion mantém fades; `:active` com escala; hover só com ponteiro fino)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Accessibility · Easing & duration · Cohesion & tokens
- **Estimated scope**: `tokens/tokens.json` (grupo `motion`), `app/globals.css` (bloco de reduced motion, seção "Hover e pressionado")

## Problem

Não há tokens de curva e duração; as quatro transições existentes usam `0.12s ease` literal. O bloco de
reduced motion apaga toda transição, inclusive os fades que ajudam a compreender uma mudança (Emil:
"fewer and gentler, not zero"). Nenhum elemento pressionável tem retorno físico ao toque.

```css
/* app/globals.css:2188-2194 — atual */
@media (prefers-reduced-motion: reduce) {
  * {
    scroll-behavior: auto !important;
    animation: none !important;
    transition: none !important;
  }
}
/* app/globals.css — seção "Hover e pressionado", atual */
button, a, summary, label.chip-check, .nearby-radius label, .product-card, .flyer-card, .searchbar, input, select {
  transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease, box-shadow 0.12s ease;
}
@media (hover: hover) { /* … estados de hover … */ }
```

## Target

```css
/* app/tokens.css (gerado) — grupo "motion" */
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
  --ease: ease;
  --dur-press: 160ms; --dur-tooltip: 125ms; --dur-menu: 180ms; --dur-state: 200ms;
  --dur-modal: 250ms; --dur-modal-exit: 190ms; --dur-sheet: 500ms; --dur-toast: 400ms;
  --motion-scale-in: 0.96;   /* escala inicial de diálogos e popovers */
  --motion-lift: 8px;        /* deslocamento de entradas */
}
/* app/globals.css — substitui o bloco de reduced motion */
@media (prefers-reduced-motion: reduce) {
  :root { --motion-scale-in: 1; --motion-lift: 0px; --dur-sheet: 200ms; }
  html { scroll-behavior: auto; }
  .skeleton::after { animation: none; }
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation-duration: 0.01ms; }
}
/* pressionar: qualquer elemento clicável, em todo dispositivo (":active" é um toque real) */
button:not(:disabled), a[href], summary, label.chip-check, .nearby-radius label {
  transition: background-color 120ms var(--ease), border-color 120ms var(--ease), color 120ms var(--ease),
    box-shadow 120ms var(--ease), transform var(--dur-press) var(--ease-out);
}
button:not(:disabled):active, a[href]:active, label.chip-check:active, .nearby-radius label:active { transform: scale(0.97); }
.product-card:has(.product-open:active) { transform: scale(0.99); }
.icon-button:not(:disabled):active, .add-button:active, .quantity button:not(:disabled):active { transform: scale(0.94); }
/* hover só com ponteiro real */
@media (hover: hover) and (pointer: fine) { /* … os estados de hover existentes, movidos para cá … */ }
```

Regras a manter de `emilkowalski/skills`: nunca `transition: all`; nunca `ease-in`; nunca `scale(0)`;
UI ≤ 300 ms (a sheet de 500 ms é a exceção nomeada); keyframes só em skeleton e spinner.

## Repo conventions to follow

- Tokens nascem em `tokens/tokens.json` (plano 000) e chegam ao CSS por `app/tokens.css`; o CSS nunca
  declara um `cubic-bezier` literal.
- A seção "Hover e pressionado" no fim de `globals.css` é o lugar dos estados de interação; ampliar ali.

## Steps

1. Adicionar o grupo `motion` ao `tokens.json` com os valores acima e regenerar `tokens.css`.
2. Substituir o bloco de reduced motion (linhas 2188–2194) pelo bloco do alvo.
3. Na seção "Hover e pressionado": trocar `0.12s ease` por `120ms var(--ease)`; acrescentar `transform
   var(--dur-press) var(--ease-out)` à lista de transições dos pressionáveis; adicionar as regras `:active`
   com `scale(0.97)` / `0.94` / `0.99` como no alvo; trocar `@media (hover: hover)` por
   `@media (hover: hover) and (pointer: fine)`.
4. Remover `transform` das transições de elementos que **não** são pressionáveis (`.searchbar`, `input`,
   `select`, `.flyer-card` como contêiner) para que o scale não vaze.
5. Confirmar que `.primary:disabled` e `button:disabled` não recebem `:active` (o seletor já exclui).

## Boundaries

- Não animar nada novo aqui (diálogos, skeletons e toasts têm planos próprios).
- Não tocar em `components/`.
- Não usar `!important`.

## Verification

- **Mechanical**: `grep -c "cubic-bezier" app/globals.css` retorna 0 (todas via `var()`); `grep -c "transition: all"` retorna 0; `grep -c "ease-in\b"` retorna 0.
- **Feel check**: clicar e segurar um botão primário, um chip, um cartão e o `+`: cada um encolhe
  levemente e volta em 160 ms; no DevTools > Rendering > "Emulate CSS prefers-reduced-motion: reduce",
  os hovers de cor continuam, nada se desloca ou escala; em "Emulate touch", passar o mouse não deixa
  hover preso (o estado some com o toque).
- **Done when**: 100% dos controles do `hover-audit` têm `:active` visível e o bloco de reduced motion não
  contém `transition: none`.
