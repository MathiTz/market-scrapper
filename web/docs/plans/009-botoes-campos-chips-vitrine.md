# 009 — Botão, campo e chip como componentes com a grade completa de estados, e uma vitrine em `/demo?vitrine=1`

- **Status**: DONE 28/09 (`components/ui/{button,field,chip}.tsx` e `components/vitrine.tsx` em `/demo?vitrine=1`; `.primary`/`.secondary` seguem como aliases de `.btn` porque `admin.tsx` os usa; `loading` mantém o rótulo e põe o spinner no lugar do ícone; `.text-link` só em links `<a>`)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Cohesion & tokens
- **Estimated scope**: `components/ui/button.tsx`, `components/ui/field.tsx`, `components/ui/chip.tsx`, `components/vitrine.tsx` (novos), `app/main.tsx`, `app/globals.css`, substituições em `components/*.tsx`

## Problem

Botões são classes soltas com alturas e raios diferentes; não há estado de carregamento; chips têm três
implementações (`.category-row button`, `.chip-check`, `.filter-chip`); nada permite ver os estados lado a lado.

```css
/* app/globals.css:342-361 — atual */
.primary,
.secondary {
  display: inline-flex; align-items: center; justify-content: center; gap: 9px;
  min-height: 44px; border-radius: 9px; padding: 11px 17px; font-weight: 600; font-size: 14px;
}
.primary { border: 1px solid var(--green); background: var(--green); color: white; }
.secondary { border: 1px solid var(--line); background: white; }
/* app/globals.css:266-275 — atual */
.category-row button,
.admin-tabs button { white-space: nowrap; border: 1px solid var(--line); border-radius: 25px; padding: 10px 19px; background: white; font-size: 14px; … }
/* app/globals.css:3112 — atual */
.chip-check { position: relative; display: inline-flex; align-items: center; padding: 8px 14px; border: 1px solid var(--line); border-radius: 999px; background: white; font-size: 14px; cursor: pointer; }
```

Alturas em uso: 44 (`.primary`), 46 (`.nearby-device`), 48 (`.nearby-dialog form input`), 36 (`.filter-chip`),
40 (`.sort-select select`), 32 (`.daily-heading .text-link`).

## Target

Grade obrigatória (PrismSystem/impeccable): **default, hover, focus-visible, active, selected, disabled,
loading, invalid**. Uma API por componente; o CSS nasce dos tokens.

```tsx
// components/ui/button.tsx — alvo
type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "negative";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: React.ReactNode;
};
export function Button({ variant = "secondary", size = "md", loading = false, icon, className = "", children, disabled, ...rest }: Props) {
  return (
    <button className={`btn btn-${variant} btn-${size} ${className}`} data-loading={loading || undefined} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="btn-spinner" aria-hidden="true" /> : icon}
      <span className="btn-label">{children}</span>
    </button>
  );
}
```

```css
/* app/globals.css — alvo */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--md-space-2); border: 1px solid transparent; border-radius: var(--md-radius-sm);
  font-weight: 600; white-space: nowrap; transition: background-color 120ms var(--ease), border-color 120ms var(--ease), color 120ms var(--ease), box-shadow 120ms var(--ease), transform var(--dur-press) var(--ease-out); }
.btn-sm { min-height: 36px; padding: 0 var(--md-space-3); font-size: var(--md-text-md); }
.btn-md { min-height: 44px; padding: 0 var(--md-space-4); font-size: var(--md-text-base); }
.btn-lg { min-height: 52px; padding: 0 var(--md-space-5); font-size: var(--md-text-base); }
.btn-primary { background: var(--md-interactive-primary-fill-default); color: var(--md-interactive-primary-text); }
.btn-secondary { background: var(--md-interactive-secondary-fill-default); border-color: var(--md-interactive-secondary-border); color: var(--md-interactive-secondary-text); }
.btn-ghost { background: transparent; color: var(--md-interactive-ghost-text); }
.btn-negative { background: transparent; color: var(--md-interactive-negative-text); }
@media (hover: hover) and (pointer: fine) {
  .btn-primary:not(:disabled):hover { background: var(--md-interactive-primary-fill-hover); }
  .btn-secondary:not(:disabled):hover { background: var(--md-interactive-secondary-fill-hover); border-color: var(--md-border-strong); }
  .btn-ghost:not(:disabled):hover { background: var(--md-interactive-ghost-fill-hover); }
  .btn-negative:not(:disabled):hover { background: var(--md-interactive-negative-fill-hover); }
}
.btn:not(:disabled):active { transform: scale(0.97); }
.btn-primary:not(:disabled):active { background: var(--md-interactive-primary-fill-pressed); }
.btn-secondary:not(:disabled):active, .btn-ghost:not(:disabled):active { background: var(--md-interactive-secondary-fill-pressed); }
.btn:disabled { background: var(--md-disabled-fill); border-color: transparent; color: var(--md-disabled-text); cursor: not-allowed; }
.btn[data-loading] { color: transparent; }                       /* keeps width; label hidden, spinner centred */
.btn[data-loading] .btn-spinner { position: absolute; width: 18px; height: 18px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: nearby-spin 0.7s linear infinite; color: var(--md-interactive-primary-text); }
.btn:focus-visible { outline: 3px solid var(--md-focus-ring); outline-offset: 2px; }
/* chips: one implementation */
.chip { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 var(--md-space-3); border: 1px solid var(--md-border-default); border-radius: var(--md-radius-pill);
  background: var(--md-surface-level-1); color: var(--md-text-primary); font-size: var(--md-text-md); font-weight: 500; transition: … (as .btn); }
.chip[data-selected] { background: var(--md-selected-fill); border-color: var(--md-selected-border); color: var(--md-selected-text); }
.chip[data-selected] .chip-check { width: 14px; opacity: 1; }  .chip .chip-check { width: 0; opacity: 0; overflow: hidden; transition: width var(--dur-press) var(--ease-out), opacity var(--dur-press) var(--ease); }
/* fields */
.field { display: grid; gap: 6px; font-size: var(--md-text-sm); font-weight: 600; color: var(--md-text-secondary); }
.field input { min-height: 44px; padding: 0 var(--md-space-3); border: 1px solid var(--md-border-default); border-radius: var(--md-radius-sm); background: var(--md-surface-level-1); font: inherit; font-size: var(--md-text-base); color: var(--md-text-primary); transition: border-color 120ms var(--ease), box-shadow 120ms var(--ease); }
@media (hover: hover) and (pointer: fine) { .field input:hover { border-color: var(--md-border-strong); } }
.field input:focus-visible { outline: none; border-color: var(--md-border-selected); box-shadow: 0 0 0 3px var(--md-selected-fill); }
.field input[aria-invalid="true"] { border-color: var(--md-text-error); }
.field input:disabled { background: var(--md-disabled-fill); color: var(--md-disabled-text); }
```

Vitrine: `components/vitrine.tsx` renderiza, em `/demo?vitrine=1`, cada componente em todos os estados
(colunas: default, hover simulado por `data-hover`, focus por `data-focus`, active, selected, disabled,
loading, invalid) mais a escala de tipo, as rampas e as sombras. É a "Components sheet" do PrismSystem e o
alvo do `hover-audit` e das capturas de regressão.

## Repo conventions to follow

- Rotas decididas em `app/main.tsx` por `window.location.pathname`; a vitrine entra pela query
  `?vitrine=1` só na rota `/demo` (nunca em `/`).
- `lucide-react` para ícones; `aria-label` obrigatório em botão só de ícone (já é convenção).
- Componentes recebem `className` extra para casos de layout (`.searchbar button`, `.add-button`).

## Steps

1. Criar `components/ui/button.tsx`, `field.tsx` (`TextField` com label, hint, `invalid`), `chip.tsx`
   (`Chip` com `selected`, `onToggle`, `removable`).
2. Substituir usos: `.primary`/`.secondary`/`.text-link` em `market.tsx`, `nearby-filter.tsx`,
   `flyer-stories.tsx`, `status-panel.tsx`, `store-location.tsx`, `list-adder.tsx`, `offer-share.tsx`
   (compartilhar vira `Button variant="ghost" icon={<Share2/>}`), `product-card.tsx` ("Onde encontrar" vira
   `Button variant="secondary" size="sm"`); `RetryButton` passa `loading={busy}`; `nearby-device` passa
   `loading={busy === "device" || busy === "lookup"}` mantendo o texto.
3. Chips: `.category-row button` → `Chip`; `.chip-check` (redes) → `Chip` com checkbox oculto para manter
   `fieldset`/`legend`; `.filter-chip` → `Chip removable`.
4. Campos: `.searchbar` mantém a forma (é a busca), mas herda foco/hover do `.field`; `PriceInput` e o campo
   de endereço usam `TextField`.
5. CSS: adicionar o alvo; apagar `.primary`, `.secondary`, `.category-row button`, `.chip-check`,
   `.filter-chip`, `.store-location-trigger`, `.share-offer-button`, `.text-link` (o que sobrar de `.text-link`
   vira `Button variant="ghost" size="sm"` ou link `<a>` com a mesma cor).
6. Criar `components/vitrine.tsx` e a rota; adicionar a cena `vitrine` ao `capture.mjs` da auditoria.

## Boundaries

- Não tocar em `admin.tsx` (fora do produto público).
- Não usar `!important`.
- Não mudar textos dos botões.

## Verification

- **Mechanical**: `npm run typecheck && npm test`; `grep -cE "className=\"(primary|secondary|text-link)"`
  em `components/*.tsx` (fora `admin.tsx`) retorna 0; `hover-audit` 100% em ponteiro fino.
- **Feel check**: na vitrine, cada linha mostra os oito estados sem "buracos"; um botão em `loading` mantém a
  largura e mostra o spinner; um chip selecionado ganha o ✓ deslizando em 160 ms; pressionar qualquer botão
  encolhe a 97%.
- **Done when**: a vitrine renderiza sem erro e a captura `1280-vitrine` está em `referencias/auditoria-ux/depois/`.
