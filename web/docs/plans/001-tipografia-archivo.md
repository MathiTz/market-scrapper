# 001 — Adotar Archivo (variável, com eixo de largura) e uma escala tipográfica de nove passos

- **Status**: DONE 27/09 (Archivo Variable auto-hospedada; escala de nove passos; preço `wdth 90` tabular)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Cohesion & tokens
- **Estimated scope**: `package.json`, `app/main.tsx`, `app/tokens.css` (via `tokens/tokens.json`), `app/globals.css` (todas as declarações `font-size`/`font-weight`/`letter-spacing`), `index.html` (preload)

## Problem

A interface usa a fonte de sistema e 26 tamanhos distintos sem papel definido.

```css
/* app/globals.css:26-33 — atual */
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
/* app/globals.css:85-90 */
h1 {
  font-size: 44px;
  line-height: 1.13;
  letter-spacing: -1.8px;
  font-weight: 750;
}
/* app/globals.css:3024 */
.compact-product .price { font-size: 24px; line-height: 1.15; margin: 6px 0 0; letter-spacing: -.6px; }
```

Tamanhos em uso (ocorrências): 9 (2), 10 (2), 11 (12), 12 (67), 13 (43), 14 (49), 15 (10), 16 (8), 17 (6),
18 (4), 19 (2), 20 (4), 21 (3), 22 (3), 23 (2), 24 (4), 25 (7), 26, 28 (2), 30 (2), 34, 37, 38, 44.

## Target

```css
/* app/tokens.css (gerado) — grupo "type" */
:root {
  --md-font-sans: "Archivo Variable", "Archivo Fallback", system-ui, sans-serif;
  --md-text-xs: 0.75rem;  --md-text-sm: 0.8125rem; --md-text-md: 0.875rem; --md-text-base: 1rem;
  --md-text-lg: 1.125rem; --md-text-xl: 1.25rem;   --md-text-2xl: 1.5rem;  --md-text-3xl: 1.75rem; --md-text-4xl: 2.125rem;
  --md-leading-tight: 1.05; --md-leading-heading: 1.2; --md-leading-ui: 1.4; --md-leading-body: 1.5;
  --md-tracking-heading: -0.015em; --md-tracking-display: -0.02em;
  --md-weight-regular: 400; --md-weight-medium: 500; --md-weight-semibold: 600; --md-weight-bold: 700;
}
/* app/globals.css */
body { font-family: var(--md-font-sans); font-size: var(--md-text-base); line-height: var(--md-leading-body); font-kerning: normal; font-optical-sizing: auto; }
h1 { font-size: var(--md-text-3xl); line-height: var(--md-leading-heading); letter-spacing: var(--md-tracking-display); font-weight: var(--md-weight-bold); text-wrap: balance; }
h2 { font-size: var(--md-text-xl); line-height: 1.25; letter-spacing: -0.01em; font-weight: 650; text-wrap: balance; }
h3 { font-size: var(--md-text-lg); line-height: 1.3; font-weight: var(--md-weight-semibold); }
p  { text-wrap: pretty; }
.price { font-size: var(--md-text-3xl); line-height: var(--md-leading-tight); letter-spacing: var(--md-tracking-display); font-weight: var(--md-weight-bold); font-variation-settings: "wdth" 90; font-variant-numeric: tabular-nums; color: var(--md-price-ink); }
.offer-value strong, .product-heading .price { font-size: var(--md-text-4xl); }
@media (max-width: 760px) { h1 { font-size: var(--md-text-2xl); } .price { font-size: var(--md-text-2xl); } .offer-value strong { font-size: var(--md-text-3xl); } }
/* fallback com métricas: evita salto de layout enquanto a fonte carrega */
@font-face { font-family: "Archivo Fallback"; src: local("Arial"); size-adjust: <calc>; ascent-override: <calc>; descent-override: <calc>; line-gap-override: <calc>; }
```

Mapa de migração dos tamanhos (aplicar em todo `globals.css`; nenhum `font-size` em px sobrevive):

| Atual (px) | Token |
|---|---|
| 9, 10, 11, 12 | `--md-text-xs` (12) — nunca abaixo disso em texto de decisão |
| 13 | `--md-text-sm` |
| 14 | `--md-text-md` |
| 15, 16, 17 | `--md-text-base` |
| 18 | `--md-text-lg` |
| 19, 20, 21 | `--md-text-xl` |
| 22, 23, 24, 25 | `--md-text-2xl` |
| 26, 28, 30 | `--md-text-3xl` |
| 34, 37, 38, 44 | `--md-text-4xl` (h1 do desktop: `3xl`) |

## Repo conventions to follow

- Fontes entram como dependência npm e são importadas em `app/main.tsx` (mesmo lugar de `./globals.css`),
  ficando no bundle do Vite (sem CDN, sem chamadas externas: o produto é PWA e não deve depender de
  fonts.googleapis.com).
- Preload no `index.html`, ao lado do `<link rel="manifest">`.

## Steps

1. `npm install @fontsource-variable/archivo@5.3.0` (com `--cache <dir isolado>`, o cache global desta
   máquina falha). Em `app/main.tsx`, antes de `./tokens.css`: `import "@fontsource-variable/archivo/wdth.css";`
   (esse arquivo declara a face com os eixos `wght` 100–900 e `wdth` 62–125; sem ele a largura 90 não funciona).
2. Conferir no arquivo woff2 instalado (`node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2`)
   se a fonte tem `tnum` (abrir em wakamaifondue.com ou `npx fontkit`); se não tiver, manter
   `font-variant-numeric: tabular-nums` (o navegador cai em dígitos proporcionais) e registrar a limitação;
   se a decisão for Golos Text, trocar o pacote por `@fontsource-variable/golos-text` e remover `wdth`.
3. Calcular as métricas do fallback com `npx fontaine` (ou `@capsizecss/metrics`) para Arial contra Archivo
   e preencher `size-adjust`, `ascent-override`, `descent-override`, `line-gap-override` no `@font-face`
   acima; não estimar à mão.
4. `index.html`: `<link rel="preload" as="font" type="font/woff2" crossorigin href="…/archivo-latin-wdth-normal.woff2">`
   (o caminho final vem do build do Vite; usar `import url from "…woff2?url"` em `main.tsx` e injetar, ou
   aceitar `font-display: swap` sem preload se o caminho com hash for um problema).
5. Adicionar o grupo `type` em `tokens/tokens.json` e regenerar `app/tokens.css`.
6. Em `globals.css`, substituir cada `font-size: Npx` pelo token da tabela, `font-weight: 750/800` por 700,
   `letter-spacing` em px por em (limite −0,02em), e remover `font-family: Arial…` de `public/offline.html`
   apenas se a fonte for auto-hospedada lá também (não é: manter `system-ui` no offline).
7. Remover as eyebrows em caixa alta com tracking listadas em `../PLANO-UI-MOTION.md` seção 4.4: os `<span
   className="eyebrow green-text">` de `market.tsx`, `store-location.tsx` e `product-range-card.tsx` viram
   `<p className="overline">` com `text-transform: none; font-size: var(--md-text-sm); color:
   var(--md-text-secondary); letter-spacing: 0;` ou são removidos quando o h1/h2 abaixo já diz o mesmo.

## Boundaries

- Não alterar textos, só estilo.
- Não adicionar segunda família nem serifa.
- Não usar `clamp()` em títulos (registro product: escala fixa em rem).
- Não carregar a fonte de CDN.

## Verification

- **Mechanical**: `grep -cE "font-size:\s*[0-9.]+px" app/globals.css` retorna 0; `npm run build` mostra os
  woff2 de Archivo nos assets; Lighthouse não aponta CLS causado por fonte.
- **Feel check**: em `/`, o preço do cartão é visivelmente mais estreito e pesado que o nome (largura 90),
  os dígitos alinham em coluna na estimativa por rede; recarregar com "Slow 3G" no DevTools: o texto em
  Arial de fallback troca para Archivo sem que as linhas quebrem em outro lugar.
- **Done when**: nenhuma ocorrência de `Arial` no CSS da aplicação, escala de nove tokens em uso, e a
  captura `390-hoje-topo` refeita mostra a hierarquia nome (18/600) → embalagem (13) → preço (28/700 wdth 90).
