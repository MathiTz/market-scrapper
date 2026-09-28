# 007 — Select, tooltip e checkbox desenhados (Base UI), com origem no gatilho

- **Status**: DONE 28/09 (Base UI só no select e no tooltip; a checkbox é `<input>` nativo desenhado, sem biblioteca; `Segmented` no raio; tooltip portalado para dentro do `<dialog>` quando o gatilho está nele; token `z-popover`)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: MEDIUM
- **Category**: Cohesion & tokens · Physicality & origin
- **Estimated scope**: `package.json` (+`@base-ui-components/react@1.0.0-rc.0`), `components/ui/select.tsx`, `components/ui/tooltip.tsx`, `components/ui/checkbox.tsx` (novos), `components/market.tsx`, `components/flyers.tsx`, `components/nearby-filter.tsx`, `components/offer-share.tsx`, `app/globals.css`

## Problem

Cinco `<select>` nativos (ordenar e desconto em `market.tsx`, mês e semana em `flyers.tsx`, região quando
houver mais de uma), checkboxes com `accent-color`, e dois tooltips por `title=` que só o mouse vê depois de
um segundo.

```tsx
// components/market.tsx — atual (ordenar)
<label className="sort-select">
  Ordenar por
  <select value={effectiveSort} onChange={(e) => { setPf((f) => ({ ...f, sort: e.target.value as SortKey })); setSortChosen(true); }}>
    {(Object.keys(sortLabels) as SortKey[]).filter((key) => key !== "relevance" || typed).map((key) => (
      <option key={key} value={key}>{sortLabels[key]}</option>
    ))}
  </select>
</label>
// components/nearby-filter.tsx:227 — atual
title={value?.point.label}
// components/offer-share.tsx:99 — atual
title="Compartilhar oferta"
```

```css
/* app/globals.css:598-609 — atual */
.checkbox { cursor: pointer; display: flex !important; flex-direction: row !important; gap: 9px; align-items: center; font-size: 14px; }
.checkbox input { width: 18px; height: 18px; accent-color: var(--green); }
```

## Target

Portões: select (dezenas/dia) → consistência espacial, 180 ms; tooltip (dezenas/dia) → rótulo, 125 ms, atraso
de 400 ms e instantâneo entre vizinhos; checkbox → indicação de estado, 160 ms. Ferramenta: Base UI
(acessibilidade, foco, `--transform-origin`) + CSS com `[data-starting-style]`/`[data-ending-style]`.

```tsx
// components/ui/select.tsx — alvo
import { Select } from "@base-ui-components/react/select";
export function SelectField<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <label className="field">
      {label}
      <Select.Root value={value} onValueChange={(v) => onChange(v as T)}>
        <Select.Trigger className="select-trigger"><Select.Value /><Select.Icon className="select-icon"><ChevronDown size={16} aria-hidden="true" /></Select.Icon></Select.Trigger>
        <Select.Portal>
          <Select.Positioner sideOffset={6} className="select-positioner">
            <Select.Popup className="select-popup">
              {options.map((o) => (
                <Select.Item key={o.value} value={o.value} className="select-item">
                  <Select.ItemIndicator className="select-check"><Check size={16} aria-hidden="true" /></Select.ItemIndicator>
                  <Select.ItemText>{o.label}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.Popup>
          </Select.Positioner>
        </Select.Portal>
      </Select.Root>
    </label>
  );
}
```

```css
/* app/globals.css — alvo */
.select-trigger { display: flex; align-items: center; justify-content: space-between; gap: var(--md-space-2); min-height: 44px; padding: 0 var(--md-space-3);
  border: 1px solid var(--md-border-default); border-radius: var(--md-radius-sm); background: var(--md-surface-level-1); font: inherit; }
.select-popup { transform-origin: var(--transform-origin); padding: var(--md-space-1); border: 1px solid var(--md-border-subtle); border-radius: var(--md-radius-sm);
  background: var(--md-surface-level-1); box-shadow: var(--md-elevation-2);
  transition: opacity var(--dur-menu) var(--ease-out), transform var(--dur-menu) var(--ease-out); }
.select-popup[data-starting-style], .select-popup[data-ending-style] { opacity: 0; transform: scale(0.95); }
.select-item { display: flex; align-items: center; gap: var(--md-space-2); min-height: 40px; padding: 0 var(--md-space-3); border-radius: var(--md-radius-xs); }
.select-item[data-highlighted] { background: var(--md-interactive-ghost-fill-hover); }
.select-item[data-selected] { color: var(--md-selected-text); font-weight: 600; }
.tooltip-popup { transform-origin: var(--transform-origin); padding: 6px 10px; border-radius: var(--md-radius-xs); background: var(--md-surface-inverse); color: var(--md-text-inverse); font-size: var(--md-text-sm);
  transition: opacity var(--dur-tooltip) var(--ease-out), transform var(--dur-tooltip) var(--ease-out); }
.tooltip-popup[data-starting-style], .tooltip-popup[data-ending-style] { opacity: 0; transform: scale(0.97); }
.tooltip-popup[data-instant] { transition-duration: 0ms; }
.checkbox-box { width: 20px; height: 20px; border: 1.5px solid var(--md-border-strong); border-radius: 5px; background: var(--md-surface-level-1); display: grid; place-items: center;
  transition: background-color var(--dur-press) var(--ease), border-color var(--dur-press) var(--ease); }
.checkbox-box[data-checked] { background: var(--md-interactive-primary-fill-default); border-color: var(--md-interactive-primary-fill-default); }
.checkbox-box svg path { stroke-dasharray: 24; stroke-dashoffset: 24; transition: stroke-dashoffset var(--dur-press) var(--ease-out); }
.checkbox-box[data-checked] svg path { stroke-dashoffset: 0; }
```

Tooltip: `Tooltip.Provider delay={400}` no nível do `Market`; cada `Tooltip.Root` só em botões de ícone
(compartilhar, setas da faixa, zoom do leitor, fechar). O `title` some. Informação de preço, condição ou
distância nunca vai para tooltip (proibido pela auditoria).

## Repo conventions to follow

- Primitivos em `components/ui/`, com classes CSS próprias (o projeto não usa Tailwind); nomes com o
  prefixo do componente (`select-`, `tooltip-`, `checkbox-`).
- `aria-label` dos ícones continua (o tooltip é complemento visual, não substitui o nome acessível).
- Encapsular o Base UI nesses três arquivos: nenhum outro componente importa `@base-ui-components` (se o rc
  mudar de API, só aqui muda).

## Steps

1. `npm install @base-ui-components/react@1.0.0-rc.0` (cache isolado); confirmar `npm run typecheck`.
2. Criar `components/ui/select.tsx`, `tooltip.tsx` (com `TooltipProvider`, `Tooltip` que recebe `label` e
   `children` e passa `[data-instant]` via `Tooltip.Popup` quando o provider está "quente") e `checkbox.tsx`
   (`Checkbox.Root` + `Checkbox.Indicator` com o SVG de 24 de comprimento de traço).
3. `market.tsx`: trocar os `<select>` de ordenar e desconto por `SelectField`; trocar os `label.checkbox`
   (condições, sem preço atual, incluir clube no detalhe) por `CheckboxField`; envolver os botões de ícone
   em `Tooltip`; remover `title` de `offer-share.tsx:99` e `nearby-filter.tsx:227` (o texto do gatilho já
   mostra o local; se cortar, o label completo vai para `aria-label`, que já existe).
4. `flyers.tsx`: mês e semana com `SelectField` (a opção desabilitada "Selecione um mês" vira `disabled` no
   `Select.Item`).
5. `nearby-filter.tsx`: o `fieldset.nearby-radius` (rádios como rótulos) vira `Segmented` (CSS próprio, sem
   Base UI): a pílula selecionada desliza com o mesmo mecanismo de medição do plano 006.
6. CSS do alvo; remover `.checkbox input { accent-color }` e `.filter-panel select`.

## Boundaries

- Não usar Base UI Dialog (os `<dialog>` nativos ficam; plano 003).
- Não colocar condição de preço, distância ou validade em tooltip.
- Não estilizar `<select>` nativo com `appearance: none` como atalho: a lista precisa do popover com origem.

## Verification

- **Mechanical**: `npm run typecheck && npm test`; fluxo "filtro de rede aplicado" e "quantidade" seguem;
  roteiro de teclado: Tab até "Ordenar por", Enter abre, setas movem, Enter escolhe, Esc fecha e o foco
  volta ao gatilho; leitor de tela anuncia "Ordenar por, Mais relevantes, combobox".
- **Feel check**: abrir o select: a lista cresce a partir do gatilho (não do centro), 180 ms; passar o mouse
  por três ícones em sequência: o primeiro tooltip espera 400 ms, os seguintes abrem na hora; marcar
  "Incluir clube…": o traço do ✓ se desenha em 160 ms.
- **Done when**: `grep -c "<select" components/market.tsx components/flyers.tsx` retorna 0 (fora `admin.tsx`,
  que fica como está); nenhum `title=` em componentes públicos.
