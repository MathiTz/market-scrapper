# 005 — Toasts com Sonner: entrada por baixo, empilhamento, arrasto e Desfazer

- **Status**: DONE 28/09 (`lib/notify.tsx`; `<Notifications>` dentro de `Market` com o deslocamento do dock; o diálogo de tamanhos fecha ao adicionar, porque o toast fica fora da top layer)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: MEDIUM
- **Category**: Interruptibility · Physicality & origin
- **Estimated scope**: `package.json` (+`sonner@2.0.8`), `lib/notify.tsx` (novo), `app/main.tsx`, `components/market.tsx` (todas as chamadas `setToast`), `app/globals.css`

## Problem

O toast é um `div` que aparece e some em corte, um de cada vez, com timer fixo; uma segunda ação substitui a
mensagem sem transição.

```tsx
// components/market.tsx:222-226 e 1826-1831 — atual
useEffect(() => {
  if (!toast) return;
  const t = setTimeout(() => setToast(""), 3200);
  return () => clearTimeout(t);
}, [toast]);
…
{toast && (
  <div className="toast" role="status">
    <Check size={19} aria-hidden="true" />
    {toast}
  </div>
)}
```

```css
/* app/globals.css:1389-1403 — atual (sem transition) */
.toast {
  position: fixed;
  bottom: 25px;
  left: 50%;
  transform: translateX(-50%);
  …
  z-index: 20;
}
```

## Target

Portão: ocasional → "retorno" e "consistência espacial" (entra por baixo, sai por baixo, arrasta para
baixo). Ferramenta: Sonner (escolha de `pick-ui-library`), em modo headless com os tokens do projeto.

```tsx
// lib/notify.tsx — alvo
import { toast, Toaster } from "sonner";
import { Check, Undo2, WifiOff } from "lucide-react";
type Options = { undo?: () => void; duration?: number; icon?: React.ReactNode };
export function notify(message: string, { undo, duration = 3200, icon }: Options = {}) {
  return toast.custom(
    (id) => (
      <div className="toast" role="status">
        {icon ?? <Check size={19} aria-hidden="true" />}
        <span>{message}</span>
        {undo && (
          <button type="button" className="toast-action" onClick={() => { undo(); toast.dismiss(id); }}>
            <Undo2 size={16} aria-hidden="true" /> Desfazer
          </button>
        )}
      </div>
    ),
    { duration: undo ? 8000 : duration },
  );
}
export const notifyOffline = (m: string) => notify(m, { icon: <WifiOff size={19} aria-hidden="true" /> });
export function Notifications() {
  return <Toaster position="bottom-center" offset={24} mobileOffset={{ bottom: 168 }} gap={8} visibleToasts={3} />;
}
```

```css
/* app/globals.css — alvo: só o visual; posição, empilhamento e gesto são do Sonner */
[data-sonner-toaster] { --width: min(420px, calc(100vw - 32px)); z-index: var(--md-z-toast); }
.toast { display: flex; align-items: center; gap: var(--md-space-2); width: var(--width); padding: var(--md-space-3) var(--md-space-4);
  background: var(--md-surface-inverse); color: var(--md-text-inverse); border-radius: var(--md-radius-sm); box-shadow: var(--md-elevation-inverse); font-size: var(--md-text-md); }
.toast > span { flex: 1; }
.toast-action { margin-left: auto; display: inline-flex; gap: 4px; align-items: center; min-height: 36px; padding: 0 var(--md-space-3); border: 0; border-radius: var(--md-radius-xs);
  background: oklch(100% 0 0 / 12%); color: inherit; font-weight: 600; }
```

Sonner já anima com transições (não keyframes): entrada `translateY(100%)` → 0 em 400 ms `ease`, saída
pelo mesmo lado, pausa em hover, arrasto para dispensar com velocidade, `aria-live` próprio. Nada disso
precisa ser reescrito.

## Repo conventions to follow

- Um único ponto de montagem global: `<Notifications />` dentro do `QueryClientProvider` em `app/main.tsx`
  (Sonner exige um só `<Toaster>`; nunca por vista).
- As mensagens continuam em `market.tsx` no mesmo lugar onde hoje há `setToast(...)`; só a chamada muda.
- A remoção da lista já guarda `undo` em estado (`setUndo({ lines, message })`) e mostra um aviso
  persistente: **manter** o aviso (informação crítica não depende de toast) e **acrescentar** o `undo` no toast.

## Steps

1. `npm install sonner@2.0.8` (cache isolado).
2. Criar `lib/notify.tsx` conforme o alvo; montar `<Notifications />` em `app/main.tsx`.
3. `market.tsx`: remover o estado `toast`, o `useEffect` do timer (222–226) e o bloco de render
   (1826–1831); trocar cada `setToast("…")` por `notify("…")`; em `remove(ids, message)` chamar
   `notify(message, { undo: () => { setLines(previous); setUndo(null); } })`; na retomada de conexão usar
   `notifyOffline`/`notify` com o texto atual.
4. CSS: substituir o bloco `.toast` (1389–1403) e as regras de mobile de `.toast` (`bottom: calc(90px…)`,
   `.has-mobile-search .toast`) pelo alvo; o deslocamento acima do dock passa a ser `mobileOffset`.
5. Conferir a sobreposição com diálogos abertos: o Toaster fica fora de qualquer `<dialog>`; como diálogos
   usam a top layer, um toast disparado com diálogo aberto fica atrás; disparar toasts só após fechar (o
   caso "Adicionar à lista" de dentro do diálogo de tamanhos deve fechar o diálogo antes de notificar).

## Boundaries

- Não estilizar por `classNames` com `!important`; usar `toast.custom` (headless), como recomenda `ask-sonner`.
- Não remover o aviso persistente "… foi removido · Desfazer" da lista.
- Não usar `richColors` nem os ícones padrão do Sonner.

## Verification

- **Mechanical**: `npm run typecheck && npm test`; `grep -c setToast components/market.tsx` retorna 0.
- **Feel check**: adicionar três produtos em sequência rápida: os toasts empilham sem reiniciar a animação
  do anterior; passar o mouse pausa o timer; arrastar para baixo dispensa; remover um item e tocar
  "Desfazer" no toast restaura a lista; no celular (390 px) o toast fica acima do dock de busca e navegação.
- **Done when**: nenhum `div.toast` renderizado por `market.tsx`; toasts entram e saem pelo mesmo lado.
