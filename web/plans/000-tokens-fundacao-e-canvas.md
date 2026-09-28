# 000 — Criar a fonte única de tokens, gerar `tokens.css` e trocar o canvas verde por branco-gelo

- **Status**: DONE 27/09 (fase 0: `tokens/`, `app/tokens.css`, `npm run tokens:check` no `prebuild`)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Cohesion & tokens
- **Estimated scope**: 3 arquivos novos (`tokens/tokens.json`, `tokens/build.mjs`, `tokens/check.mjs`), 1 gerado (`app/tokens.css`), edições em `app/globals.css`, `app/main.tsx`, `package.json`

## Problem

A cor não tem sistema: 84 literais hex em `app/globals.css`, 17 variáveis avulsas em `:root` e mais de
quinze tons de verde-claro usados como fundo de página, painéis, avisos, seleções e hover. O proprietário
pediu fundo branco ou branco com 3% de "gelo" e nenhum verde como superfície.

```css
/* app/globals.css:1-19 — atual */
:root {
  --green: #116249;
  --dark: #173d30;
  --lime: #d9ed92;
  --bg: #f6f8f7;
  --line: #dde6e1;
  --text: #1e332a;
  --muted: #5b6c62;
  --white: #fff;
  --amber: #865510;
  --focus: #173d30;
  --hover-bg: #eef4f0;
  --hover-bg-strong: #e3ede6;
  --press-bg: #d6e5da;
  --line-hover: #a9bfb1;
  --green-hover: #0d4f3b;
  --green-press: #0a3f2f;
}
```

Superfícies verdes a eliminar (todas em `app/globals.css`; procurar pelo hex): `#f6f8f7` (body), `#eaf1ed`
(`.empty`, `.loading`, skeleton), `#edf2ef` (`.notice`), `#e3ede6` (`.desktop-nav button.selected`,
`--hover-bg-strong`), `#f0f6ec` (`.add-button`, `.size-row-add`, `.shared-offer`), `#e5f1e5` (`.badge.green`),
`#eef4f0` (`--hover-bg`), `#e8f0eb` (`.store-mark`), `#f4f8e9` (`.daily-deal`), `#edf6ef` (aba de rede
selecionada), `#f3f7f3` (`.flyer-open-hint`), `#edf2ee` (`.flyer-open`, `.flyer-card-player`, `.badge`),
`#eaf3ee` (`.chip-check.selected`, `.suggestions li:hover`), `#dff3e6` (`.badge.good`), `#f0f3f1`
(`.product-placeholder`, `.nearby-dialog-heading .icon-button`), `#e4eae6` (`.flyer-viewport`), `#e7ece8`
(`.flyer-cover`), `#d6e5da` (`--press-bg`).

## Target

Três camadas (PrismSystem): fundação e paleta em OKLCH no JSON; semântica referencia a paleta; o CSS só
consome semântica. Canvas `oklch(98.8% 0.003 240)` (≈ `#f9fbfd`). Nenhum passo verde em fundo, hover ou
painel; o verde fica em `interactive-primary-*`, `selected-*`, `text-brand`, `focus-ring`.

```json
// tokens/tokens.json — estrutura (valores completos na seção 3 de ../PLANO-UI-MOTION.md)
{
  "$schema": "./tokens.schema.json",
  "foundation": {
    "color": {
      "neutral": { "0": "#ffffff", "50": "oklch(98.8% 0.003 240)", "100": "oklch(96.5% 0.005 240)", "200": "oklch(92% 0.008 240)", "300": "oklch(86% 0.01 240)", "400": "oklch(70% 0.015 235)", "500": "oklch(55% 0.02 230)", "600": "oklch(45% 0.02 230)", "700": "oklch(35% 0.02 230)", "800": "oklch(28% 0.015 230)", "900": "oklch(22% 0.015 230)" },
      "brand":   { "50": "oklch(97% 0.02 163)", "100": "oklch(94% 0.045 163)", "200": "oklch(88% 0.08 163)", "300": "oklch(78% 0.11 163)", "400": "oklch(62% 0.12 163)", "500": "oklch(50% 0.11 163)", "600": "#116249", "700": "oklch(36% 0.085 163)", "800": "oklch(30% 0.07 163)", "900": "#173d30" },
      "amber":   { "50": "oklch(96% 0.04 80)", "100": "oklch(92% 0.07 80)", "600": "oklch(45% 0.1 70)", "700": "oklch(38% 0.09 70)" },
      "lime":    { "100": "oklch(92% 0.14 120)", "900": "oklch(30% 0.08 130)" },
      "red":     { "50": "oklch(96% 0.02 25)", "600": "oklch(50% 0.18 25)", "700": "oklch(42% 0.16 25)" },
      "blue":    { "50": "oklch(96% 0.02 250)", "700": "oklch(40% 0.12 255)" }
    },
    "space": { "1": "4px", "2": "8px", "3": "12px", "4": "16px", "5": "20px", "6": "24px", "8": "32px", "10": "40px", "12": "48px", "16": "64px" },
    "radius": { "xs": "6px", "sm": "10px", "md": "14px", "lg": "20px", "pill": "999px" },
    "z": { "dropdown": 10, "sticky": 20, "dock": 30, "backdrop": 40, "modal": 50, "toast": 60, "tooltip": 70 }
  },
  "semantic": {
    "surface-canvas": "{neutral.50}", "surface-level-1": "{neutral.0}", "surface-level-2": "{neutral.100}", "surface-inverse": "{neutral.900}",
    "text-primary": "{neutral.900}", "text-secondary": "{neutral.600}", "text-tertiary": "{neutral.500}", "text-inverse": "{neutral.0}", "text-brand": "{brand.700}", "text-warning": "{amber.700}", "text-error": "{red.700}", "text-link": "{brand.700}",
    "border-subtle": "{neutral.200}", "border-default": "{neutral.300}", "border-strong": "{neutral.400}", "border-selected": "{brand.600}",
    "interactive-primary-fill-default": "{brand.600}", "interactive-primary-fill-hover": "{brand.700}", "interactive-primary-fill-pressed": "{brand.800}", "interactive-primary-text": "{neutral.0}",
    "interactive-secondary-fill-default": "{neutral.0}", "interactive-secondary-fill-hover": "{neutral.100}", "interactive-secondary-fill-pressed": "{neutral.200}", "interactive-secondary-border": "{neutral.300}", "interactive-secondary-text": "{neutral.900}",
    "interactive-ghost-fill-hover": "{neutral.100}", "interactive-ghost-fill-pressed": "{neutral.200}", "interactive-ghost-text": "{brand.700}",
    "interactive-negative-fill-hover": "{red.50}", "interactive-negative-text": "{red.700}",
    "selected-fill": "{brand.50}", "selected-border": "{brand.600}", "selected-text": "{brand.800}",
    "disabled-fill": "{neutral.100}", "disabled-text": "{neutral.500}",
    "focus-ring": "{brand.900}",
    "messaging-info-fill": "{blue.50}", "messaging-info-text": "{blue.700}", "messaging-success-fill": "{brand.50}", "messaging-success-text": "{brand.700}", "messaging-warning-fill": "{amber.50}", "messaging-warning-border": "{amber.100}", "messaging-warning-text": "{amber.700}", "messaging-error-fill": "{red.50}", "messaging-error-text": "{red.700}",
    "price-ink": "{neutral.900}", "price-unit": "{neutral.600}", "price-regular": "{neutral.500}", "deal-fill": "{lime.100}", "deal-text": "{lime.900}", "condition-fill": "{amber.50}", "condition-text": "{amber.700}"
  },
  "elevation": {
    "1": "0 1px 2px oklch(22% 0.015 230 / 6%), 0 8px 24px oklch(22% 0.015 230 / 6%)",
    "2": "0 2px 6px oklch(22% 0.015 230 / 8%), 0 12px 32px oklch(22% 0.015 230 / 10%)",
    "3": "0 8px 24px oklch(22% 0.015 230 / 12%), 0 24px 64px oklch(22% 0.015 230 / 16%)",
    "inverse": "0 8px 30px oklch(22% 0.015 230 / 25%)"
  },
  "pairs": [
    ["text-primary", "surface-canvas", 4.5], ["text-secondary", "surface-canvas", 4.5], ["text-secondary", "surface-level-2", 4.5],
    ["interactive-primary-text", "interactive-primary-fill-default", 4.5], ["interactive-primary-text", "interactive-primary-fill-hover", 4.5],
    ["selected-text", "selected-fill", 4.5], ["condition-text", "condition-fill", 4.5], ["deal-text", "deal-fill", 4.5],
    ["messaging-warning-text", "messaging-warning-fill", 4.5], ["messaging-error-text", "messaging-error-fill", 4.5],
    ["focus-ring", "surface-canvas", 3], ["focus-ring", "surface-level-1", 3], ["focus-ring", "surface-level-2", 3],
    ["border-default", "surface-level-1", 3]
  ]
}
```

`tokens/build.mjs` gera `app/tokens.css`:

```css
/* app/tokens.css — GERADO por tokens/build.mjs; não editar à mão */
:root {
  --md-neutral-0: #ffffff; /* … toda a paleta, hex resolvido do OKLCH com mapeamento de gamut (redução de chroma até caber em sRGB) */
  --md-surface-canvas: var(--md-neutral-50);
  /* … toda a semântica como var() da paleta */
  --md-elevation-1: 0 1px 2px …;
  --md-space-1: 4px; /* … */
  --md-radius-sm: 10px; /* … */
  --md-z-modal: 50; /* … */
}
```

## Repo conventions to follow

- Scripts do projeto vivem em `package.json > scripts` e rodam com Node 24 (`"type": "module"`); usar
  `node tokens/build.mjs` sem dependências novas (a conversão OKLCH → sRGB é o algoritmo do CSS Color 4,
  ~40 linhas: OKLab → LMS → RGB linear → gama sRGB; se o resultado sair de [0,1], reduzir chroma por busca
  binária até caber).
- `app/main.tsx` importa `./globals.css`; importar `./tokens.css` **antes** dele.
- Comentários em inglês, como o restante do CSS.

## Steps

1. Criar `tokens/tokens.json` com o conteúdo do alvo (completar o que está elidido com as tabelas de
   `../PLANO-UI-MOTION.md` seções 3.2 e 3.3).
2. Criar `tokens/build.mjs`: lê o JSON, resolve `{grupo.passo}`, converte OKLCH em hex, escreve
   `app/tokens.css` com o cabeçalho "GERADO" e, para a migração, os **aliases legados** no fim:
   `--green: var(--md-interactive-primary-fill-default); --dark: var(--md-brand-900); --lime: var(--md-deal-fill);
   --bg: var(--md-surface-canvas); --line: var(--md-border-subtle); --text: var(--md-text-primary);
   --muted: var(--md-text-secondary); --white: var(--md-surface-level-1); --amber: var(--md-text-warning);
   --focus: var(--md-focus-ring); --hover-bg: var(--md-interactive-secondary-fill-hover);
   --hover-bg-strong: var(--md-interactive-ghost-fill-hover); --press-bg: var(--md-interactive-ghost-fill-pressed);
   --line-hover: var(--md-border-strong); --green-hover: var(--md-interactive-primary-fill-hover);
   --green-press: var(--md-interactive-primary-fill-pressed);`
3. Criar `tokens/check.mjs` com dois modos: `contrast` (WCAG 2.x sobre `pairs`; imprime a tabela e sai com
   código 1 se algum par ficar abaixo do mínimo) e `literals` (procura `#[0-9a-f]{3,8}`, `rgb(`, `oklch(` em
   `app/globals.css` e `components/**/*.tsx`, ignorando `app/tokens.css` e os caminhos em `tokens/allow.json`;
   sai com 1 se encontrar). Começar com `allow.json` contendo `app/globals.css` inteiro e ir removendo a
   exceção conforme os passos 6–7 avançam; ao fim deste plano, `globals.css` não está mais na lista.
4. `package.json`: `"tokens": "node tokens/build.mjs"`, `"tokens:check": "node tokens/check.mjs"`,
   `"prebuild": "npm run tokens && npm run tokens:check"`. Importar `./tokens.css` em `app/main.tsx` antes de
   `./globals.css`.
5. Substituir o bloco `:root` de `globals.css` (linhas 1–19) por um comentário apontando para `tokens.css`
   (os aliases legados mantêm o resto do arquivo funcionando).
6. Trocar cada hex da lista de superfícies verdes pelo token semântico: body → `var(--md-surface-canvas)`;
   `.empty`, `.loading`, `.notice`, `.filter-panel`, `.coverage`, `.inactive-offers` → `var(--md-surface-level-2)`
   ou `level-1` com `border-subtle`; hover/pressed → `interactive-*`; seleções (`.chip-check.selected`,
   `.desktop-nav button.selected`, aba de rede selecionada, `.shared-offer`) → `selected-fill/border/text`;
   `.badge.green` → `messaging-success-*`; `.badge.amber`/`.notice.amber` → `messaging-warning-*`;
   `.daily-deal` → `surface-level-1` + `border-selected`; `.deal-note em` → `deal-*`; `.store-mark`,
   `.product-placeholder`, `.flyer-viewport`, `.flyer-cover`, `.flyer-open` → `surface-level-2`.
7. Trocar os demais literais (`#42594b`, `#53685c`, `#465f50`, `#294737`, `#825619`, `#715016`, `#533b0f`,
   `#a3372b`, `#c0392b`, `#1d4f91`, `#e3eefc`, `#0f6b46`…) por `text-secondary`, `text-warning`,
   `text-error`, `messaging-info-*` etc., e `box-shadow` por `--md-elevation-*`.
8. Rodar `npm run tokens && npm run tokens:check`; corrigir qualquer par reprovado **subindo a lightness do
   texto ou descendo a do fundo no JSON**, nunca no CSS.

## Boundaries

- Não alterar marcação nem lógica em `components/`.
- Não mudar os valores de `brand.600` (`#116249`) e `brand.900` (`#173d30`): são a marca.
- Não introduzir dark mode (o JSON já suporta uma segunda rampa, mas fica para depois).
- Não instalar dependências para o build de tokens.

## Verification

- **Mechanical**: `npm run tokens` gera `app/tokens.css` sem erro; `npm run tokens:check` passa nos dois
  modos; `npm run typecheck && npm test && npm run build` verdes.
- **Feel check**: abrir `/` a 390 e 1280 px: o fundo é branco-gelo, cartões brancos com fio; nenhum painel
  verde; o verde só aparece em botões primários, chips selecionados, pílula da aba ativa e wordmark.
  Comparar com `referencias/auditoria-ux/depois/390-hoje-topo.png`.
- **Done when**: `grep -cE "#[0-9a-fA-F]{3,8}" app/globals.css` retorna 0 e o check de contraste passa.
