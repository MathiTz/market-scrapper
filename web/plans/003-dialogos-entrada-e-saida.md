# 003 — Diálogos nativos com entrada, saída e backdrop em transição

- **Status**: DONE 28/09 (`components/ui/use-dialog.ts`: a saída roda com `data-closing` enquanto o diálogo ainda está aberto; `@starting-style` precisa da mesma especificidade da regra aberta, senão não anima; fallback de 460 ms)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Physicality & origin · Missed opportunities
- **Estimated scope**: `components/ui/use-dialog.ts` (novo), `components/store-location.tsx`, `components/product-range-card.tsx`, `components/nearby-filter.tsx`, `components/flyer-stories.tsx`, `app/globals.css`

## Problem

Os quatro diálogos abrem com `showModal()` e fecham desmontando o elemento: nenhum tem transição, e o
backdrop aparece e some em corte.

```tsx
// components/store-location.tsx:39-50 — atual (o mesmo padrão em product-range-card.tsx:109-120 e flyer-stories.tsx:62-72)
useEffect(() => {
  const dialog = ref.current!;
  const overflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  dialog.showModal();
  return () => {
    dialog.close();
    document.body.style.overflow = overflow;
    if (opener.current?.isConnected) opener.current.focus();
  };
}, [opener]);
// components/store-location.tsx — o pai desmonta na hora:
{open && <LocationDialog … onClose={() => setOpen(false)} />}
```

```css
/* app/globals.css:2261-2263 — atual */
.location-dialog::backdrop {
  background: rgb(15 31 23 / 65%);
}
```

## Target

Portão: ocasional → propósito "evitar salto" e "consistência espacial". Ferramenta: CSS nativo
(`@starting-style` + `transition-behavior: allow-discrete`), sem biblioteca. Modal fica centrado
(`transform-origin: center` é a exceção correta).

```css
/* app/globals.css — todos os diálogos */
dialog.location-dialog, dialog.nearby-dialog, dialog.flyer-dialog {
  opacity: 0;
  transform: scale(var(--motion-scale-in));
  transition:
    opacity var(--dur-modal-exit) var(--ease-out),
    transform var(--dur-modal-exit) var(--ease-out),
    overlay var(--dur-modal-exit) allow-discrete,
    display var(--dur-modal-exit) allow-discrete;
}
dialog[open]:not([data-closing]) {
  opacity: 1;
  transform: scale(1);
  transition-duration: var(--dur-modal);
  @starting-style { opacity: 0; transform: scale(var(--motion-scale-in)); }
}
dialog::backdrop {
  background: oklch(22% 0.015 230 / 0%);
  transition: background var(--dur-modal-exit) var(--ease-out), overlay var(--dur-modal-exit) allow-discrete, display var(--dur-modal-exit) allow-discrete;
}
dialog[open]:not([data-closing])::backdrop {
  background: oklch(22% 0.015 230 / 55%);
  transition-duration: var(--dur-modal);
  @starting-style { background: oklch(22% 0.015 230 / 0%); }
}
```

```ts
// components/ui/use-dialog.ts — alvo
import { useCallback, useEffect, useRef } from "react";
/** Opens a native <dialog> as a modal and closes it after its exit transition ends. */
export function useDialog(open: boolean, onClosed: () => void, opener?: React.RefObject<HTMLElement | null>) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => { document.body.style.overflow = overflow; };
  }, [open]);
  const requestClose = useCallback(() => {
    const dialog = ref.current;
    if (!dialog || dialog.dataset.closing) return;
    dialog.dataset.closing = "true";
    const done = () => {
      dialog.removeEventListener("transitionend", done);
      delete dialog.dataset.closing;
      dialog.close();
      if (opener?.current?.isConnected) opener.current.focus({ preventScroll: true });
      onClosed();
    };
    dialog.addEventListener("transitionend", done, { once: true });
    setTimeout(done, 260); // safety: browsers without allow-discrete still close
  }, [onClosed, opener]);
  return { ref, requestClose };
}
```

Uso: `onCancel={(e) => { e.preventDefault(); requestClose(); }}`, botão fechar → `requestClose()`, clique no
fundo → `requestClose()`. O pai continua desmontando em `onClosed`. Saída = 190 ms (75% da entrada de 250 ms).

## Repo conventions to follow

- Diálogos são `<dialog>` nativos com `showModal()`, `onCancel` que chama `preventDefault`, foco devolvido
  ao botão que abriu (`opener.current?.focus()`), rolagem do body travada. Manter tudo isso; só o timing muda.
- Exemplar de foco devolvido: `components/nearby-filter.tsx:73-78` (`close()`).

## Steps

1. Criar `components/ui/use-dialog.ts` com o hook do alvo.
2. `store-location.tsx`: substituir o `useEffect` (39–50) por `const { ref, requestClose } = useDialog(true, onClose, opener);`
   e trocar todo `onClose()` interno por `requestClose()`.
3. `product-range-card.tsx`: mesmo tratamento; o estado `open` do card passa a fechar por `requestClose`.
4. `flyer-stories.tsx` (`FlyerDialog`): mesmo tratamento; `onClose` só é chamado por `requestClose`.
5. `nearby-filter.tsx`: o diálogo já fica sempre montado; em `close()` (73–78) trocar `dialog.current?.close()`
   por `requestClose()` e mover `cancelPending()` e `setOpened(false)` para o `onClosed`.
6. CSS: adicionar o bloco do alvo; remover os três `::backdrop` antigos (672, 2261, 2467) em favor do genérico.
7. Testar no Firefox (suporte a `allow-discrete` desde a 129): se a saída não animar, o `setTimeout` de
   260 ms garante o fechamento.

## Boundaries

- Não trocar `<dialog>` por biblioteca.
- Não animar `width`/`height`; só `opacity`, `transform` e o backdrop.
- Não mudar o conteúdo dos diálogos.
- `.flyer-dialog` mantém `transform-origin: center`; nenhum diálogo usa origem no gatilho (são modais).

## Verification

- **Mechanical**: `npm run typecheck && npm test`; o roteiro de fluxos (`referencias/auditoria-ux/scripts/flows.mjs`) continua 62/62, em especial "Esc fecha e devolve o foco".
- **Feel check**: abrir "Onde encontrar": o cartão cresce de 96% para 100% com o fundo escurecendo junto
  (250 ms); fechar por Esc, pelo X e pelo fundo: encolhe e some em 190 ms, o foco volta ao botão. No
  DevTools > Animations a 10%: opacidade e escala terminam no mesmo frame; o backdrop não "pisca" antes
  do conteúdo. Com reduced motion: só o fade.
- **Done when**: os quatro diálogos entram e saem com transição e nenhum `showModal()` fica fora do hook.
