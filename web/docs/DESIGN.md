---
name: Mercado em Dia
description: Consultor de preços de supermercado em Fortaleza, com tipografia de etiqueta de preço sobre um canvas branco-gelo
colors:
  ice-canvas: "#f9fbfd"
  paper: "#ffffff"
  panel: "#f1f4f6"
  hairline: "#e0e5e9"
  field-border: "#7f8b92"
  ink: "#131c20"
  ink-secondary: "#4a585e"
  ink-tertiary: "#66747b"
  brand-green: "#116249"
  brand-green-deep: "#004a31"
  brand-green-pressed: "#003824"
  brand-green-ink: "#173d30"
  selection-mist: "#eafaf1"
  condition-amber: "#fff0d7"
  condition-amber-ink: "#5e3900"
  deal-lime: "#d9f283"
  deal-lime-ink: "#203501"
  error-red: "#90101a"
  error-red-mist: "#ffedeb"
  info-blue: "#0e4786"
  info-blue-mist: "#e8f3ff"
  demo-yellow: "#f9d280"
typography:
  display:
    fontFamily: "Archivo Variable, Archivo Fallback, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Archivo Variable, Archivo Fallback, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo Variable, Archivo Fallback, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Archivo Variable, Archivo Fallback, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "Archivo Variable, Archivo Fallback, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "20px"
  pill: "999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
  10: "40px"
  12: "48px"
  16: "64px"
components:
  button-primary:
    backgroundColor: "{colors.brand-green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.brand-green-deep}"
  button-primary-active:
    backgroundColor: "{colors.brand-green-pressed}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.panel}"
  chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "40px"
  chip-selected:
    backgroundColor: "{colors.selection-mist}"
    textColor: "{colors.brand-green-pressed}"
  card:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.md}"
    padding: "12px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "44px"
  badge-condition:
    backgroundColor: "{colors.condition-amber}"
    textColor: "{colors.condition-amber-ink}"
    rounded: "{rounded.xs}"
    padding: "4px 8px"
  badge-deal:
    backgroundColor: "{colors.deal-lime}"
    textColor: "{colors.deal-lime-ink}"
    rounded: "{rounded.pill}"
    padding: "1px 7px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
---

# Design System: Mercado em Dia

Gerado ao fim da fase 0 do [PLANO-UI-MOTION.md](PLANO-UI-MOTION.md) (27/09/2026) a partir de
`tokens/tokens.json` e `app/globals.css`. A fonte de verdade dos valores é `app/tokens.css`; este documento
descreve como aplicá-los. O Nome-Norte e a linguagem qualitativa são uma proposta a confirmar com o
proprietário.

## 1. Overview

**Creative North Star: "A etiqueta de gôndola"**

Tudo o que a interface faz cabe no gesto de ler uma etiqueta de preço no supermercado: o número domina, a
unidade e a condição vêm pequenas mas legíveis, o resto do mundo fica em segundo plano. O sistema é uma UI
de utilidade (registro *product*): neutros frios quase brancos, uma só família tipográfica com o preço em
largura semicondensada, um acento verde reservado à ação e à seleção. Densidade média, cartões só onde o
cartão é o produto (o resultado da busca, a faixa de ofertas), listas com fio no restante.

O sistema rejeita explicitamente o que `PRODUCT.md` lista como anti-referência: linguagem de checkout,
superfícies verdes, cara de protótipo (controles do navegador, fonte de sistema, cortes secos), landing page
de SaaS (eyebrows em caixa alta em toda seção, cartões idênticos, gradiente em texto, vidro decorativo) e
motion decorativa.

**Key Characteristics:**
- Canvas branco-gelo (`#f9fbfd`) e papel branco com fio de 1 px; nenhum fundo tingido de verde.
- Archivo Variable em uma escala fixa de nove passos; o preço é a única licença tipográfica (largura 90,
  peso 700, numerais tabulares).
- Verde em ≤ 10% da tela: botão primário, pílula de seleção, marca, links de ação.
- Âmbar significa condição ou alerta; lima significa desconto informado pela loja; nada além disso.
- Movimento curto (≤ 300 ms) que conta abertura, fechamento e carregamento; hover só com ponteiro real;
  reduced motion reduz, não zera.

## 2. Colors: a paleta gelo-e-verde

Neutros frios de chroma mínimo carregam a página; o verde da marca é preservado e só aparece como acento.

### Primary
- **Verde da marca** (`#116249`): botão primário, borda de seleção, wordmark. Preservado do produto original.
- **Verde profundo** (`#004a31`): hover do primário, texto de link e de ação ("Onde encontrar", "Ver todas").
- **Verde pressionado** (`#003824`): estado `:active` do primário; texto sobre a névoa de seleção.
- **Tinta verde** (`#173d30`): anel de foco (≥ 10:1 sobre qualquer superfície clara).

### Secondary
- **Âmbar de condição** (`#fff0d7` fundo · `#5e3900` texto): "Só para membros do PinClube", avisos de atenção.
- **Lima de desconto** (`#d9f283` fundo · `#203501` texto): o selo "25% OFF" informado pela loja.
- **Amarelo da demonstração** (`#f9d280`): a faixa "modo demonstrativo", e nada mais.

### Tertiary
- **Vermelho de erro** (`#90101a` · névoa `#ffedeb`): campo inválido, remover da lista.
- **Azul informativo** (`#0e4786` · névoa `#e8f3ff`): "Mais perto da referência".

### Neutral
- **Canvas gelo** (`#f9fbfd`): fundo da página. Branco com 3% de tinta fria.
- **Papel** (`#ffffff`): cartões, diálogos, campos, cabeçalho.
- **Painel** (`#f1f4f6`): filtros, avisos neutros, esqueletos, fundo do leitor de encartes, hover de botões secundários.
- **Fio** (`#e0e5e9`): borda de cartão e divisor de lista.
- **Borda de campo** (`#7f8b92`): campos e botões secundários; 3,5:1 sobre papel (WCAG 1.4.11).
- **Tinta** (`#131c20`): texto principal e preços.
- **Tinta secundária** (`#4a585e`): metadados, overlines, unidade do preço (7:1 sobre o canvas).
- **Tinta terciária** (`#66747b`): preço riscado, texto desabilitado, "Sem foto" (4,8:1; nunca em texto de decisão pequeno).

### Named Rules
**The No Green Surface Rule.** Nenhuma superfície (página, painel, cartão, hover) leva verde. O verde é
ação, seleção e marca; a névoa `#eafaf1` só existe sob um elemento selecionado.

**The Pairs Rule.** Todo par texto/fundo do sistema está declarado em `tokens/tokens.json > pairs` e
`npm run tokens:check` reprova qualquer par abaixo de 4,5:1 (texto) ou 3:1 (foco, borda de campo). Um novo
par sem entrada na lista não existe.

## 3. Typography

**Display Font:** Archivo Variable (com Archivo Fallback, métricas de Arial ajustadas)
**Body Font:** Archivo Variable
**Label/Mono Font:** nenhum; numerais tabulares da própria Archivo

**Character:** uma grotesca de sinalização, brasileira, com um eixo de largura. Em largura normal ela é
discreta e legível; em largura 90 e peso 700 vira a etiqueta de preço do encarte. Uma família, dois
registros, sem serifa.

### Hierarchy
- **Display** (700, 2.125rem/34px, 1.05, −0,02em): o preço no detalhe do produto. No mobile, 1.75rem.
- **Headline** (700, 1.75rem/28px, 1.2, −0,02em): h1 de vista ("Ofertas do dia.", "Minha lista.") e o preço
  no cartão (largura 90, tabular). No mobile, 1.5rem.
- **Title** (650, 1.25rem/20px, 1.25, −0,01em): h2 de seção; nome do produto no cartão em 1.125rem/600.
- **Body** (400, 1rem/16px, 1.5): parágrafos, campos, botões; medida máxima 65ch.
- **Label** (500, 0.8125rem/13px, 1.4): overlines em caixa normal, metadados de cartão, chips; 0.875rem/500
  para UI secundária; 0.75rem apenas para horário, origem e notas (nunca abaixo).

### Named Rules
**The Price Licence Rule.** Só o preço usa `"wdth" 90`; todo o resto fica na largura 100. Um segundo uso
da largura estreita dilui a assinatura.

**The No Eyebrow Rule.** Não existem rótulos em caixa alta com tracking acima de títulos. A frase acima do
h1 é uma overline em caixa normal, 13 px, tinta secundária, ou não existe.

## 4. Elevation

Plano por padrão, com sombras tingidas com a tinta (nunca preto puro) só como resposta a estado. O cartão
em repouso é papel com fio; o hover eleva; popovers e diálogos flutuam; o toast é o único elemento escuro.

### Shadow Vocabulary
- **elevation-1** (`0 1px 2px oklch(22% 0.015 230 / 6%), 0 8px 24px oklch(22% 0.015 230 / 6%)`): cartão em hover, barra de busca em foco.
- **elevation-2** (`0 2px 6px … / 8%, 0 12px 32px … / 10%`): popover, tooltip, lista de sugestões.
- **elevation-3** (`0 8px 24px … / 12%, 0 24px 64px … / 16%`): diálogo e bottom sheet.
- **elevation-inverse** (`0 8px 30px … / 25%`): toast sobre o conteúdo.
- **scrim** (`oklch(22% 0.015 230 / 55%)`): fundo dos diálogos.

### Named Rules
**The Flat-At-Rest Rule.** Nada tem sombra parado. Se um cartão parece "flutuar" sem o ponteiro sobre
ele, a sombra está errada.

## 5. Components

### Buttons
- **Shape:** cantos suaves (10px), altura 44px (36 sm, 52 lg), texto 600.
- **Primary:** verde da marca com texto branco; hover verde profundo; `:active` verde pressionado e
  `scale(0.97)` em 160 ms; `loading` põe o spinner no lugar do ícone e mantém o rótulo (que diz o que está
  acontecendo); `disabled` painel + tinta terciária.
- **Hover / Focus:** hover só com ponteiro fino; foco é anel de 3px tinta verde a 2px do controle.
- **Secondary:** papel com borda de campo; hover painel. **Ghost:** transparente, texto verde profundo,
  hover painel. **Negative:** texto vermelho, hover névoa vermelha.

### Chips
- **Style:** pílula (999px), 40px, papel com borda de campo, texto 500.
- **State:** selecionado = névoa de seleção + borda verde + ✓ que desliza; filtro ativo = mesmo desenho com × para remover.

### Cards / Containers
- **Corner Style:** 14px (cartão), 20px (diálogo e sheet).
- **Background:** papel sobre o canvas gelo.
- **Shadow Strategy:** nenhuma em repouso; `elevation-1` em hover (sem deslocar).
- **Border:** fio `#e0e5e9`; cartão em destaque ("oferta do dia") usa borda verde, nunca fundo verde.
- **Internal Padding:** 12px no cartão compacto, 18–22px em linhas de comparação e painéis.

### Inputs / Fields
- **Style:** papel, borda de campo 1px, cantos 10px, altura 44px, texto 16px (o iOS não dá zoom).
- **Focus:** borda verde + halo de 3px na névoa de seleção; sem `outline` nativo.
- **Error / Disabled:** borda vermelha com dica abaixo; painel com tinta terciária.

### Navigation
- **Desktop:** quatro abas em texto 600; a ativa recebe pílula na névoa de seleção com texto verde pressionado.
- **Mobile:** dock branco fixo com fio superior, ícone + rótulo 12px, indicador de 3px verde sobre a aba ativa, contador verde na lista.
- **Estados:** hover painel (ponteiro fino), `:active` escala 0.97, `aria-current="page"`.

### Price block (signature)
Preço em Archivo largura 90, 700, tabular, tinta; preço riscado em tinta terciária com traço de 1,5px;
selo de desconto em lima; unidade (`/kg`, `/L`) em 13px tinta secundária; condição em âmbar logo abaixo.

### Select, tooltip, checkbox, segmentado
- **Select:** gatilho com a forma do campo; a lista nasce do gatilho (`--transform-origin`) em 180 ms e
  some pelo mesmo caminho; item realçado em painel, selecionado em texto verde pressionado com ✓.
- **Tooltip:** só em controles de ícone, tinta invertida, 125 ms; o primeiro espera 400 ms, os vizinhos abrem
  na hora. Preço, condição, validade e distância nunca vão para tooltip.
- **Checkbox:** caixa de 20px com cantos 6px; marcada = fundo verde e ✓ que se desenha em 160 ms.
- **Segmentado:** trilho em painel, pílula branca com `elevation-1` que desliza em 180 ms.

### Dialogs, sheets, toasts, skeletons
- **Diálogo (≥ 760 px):** centrado, entra em 250 ms de 96% para 100% com o fundo escurecendo junto, sai em 190
  ms; Esc, × e fundo saem do mesmo jeito e devolvem o foco.
- **Sheet (< 760 px):** sobe em 500 ms na curva `--ease-drawer`, cantos 20px em cima, alça de 36×4, página
  recua a 96%; puxar para baixo fecha (40% da altura ou um flick), soltar antes disso volta com mola leve.
- **Toast:** tinta invertida, entra e sai por baixo em 400 ms, empilha até três, pausa no hover, arrasta para
  dispensar; "Desfazer" em toast e no aviso persistente da lista.
- **Skeleton:** blocos em painel com a forma do conteúdo e uma onda de 1,5 s (só `transform`); fotos entram
  em fade de 200 ms sobre o bloco; a busca mantém a grade atual, esmaecida e desfocada, até o próximo resultado.
- **View Transitions:** a foto tocada vira o herói do produto (250 ms); trocar de aba é um crossfade de 150 ms
  com a pílula deslizando; sem suporte ou com movimento reduzido, tudo é instantâneo.

## 6. Do's and Don'ts

### Do:
- **Do** consumir apenas `var(--md-*)` e os tokens de motion; `npm run tokens:check` reprova hex, `rgb()` e `oklch()` fora de `app/tokens.css`.
- **Do** reservar o verde a botão primário, seleção, marca e links de ação (≤ 10% da tela).
- **Do** dar a todo pressionável `:active { transform: scale(0.97) }` em 160 ms e hover só sob `(hover: hover) and (pointer: fine)`.
- **Do** usar a escala de nove tamanhos e a de cinco raios; um valor fora delas é um bug de sistema.
- **Do** escrever preços com `tabular-nums` e largura 90; unidades e condições ao lado, legíveis, nunca em tooltip.

### Don't:
- **Don't** pintar fundo de página, painel, cartão ou hover de verde: o produto anterior fazia isso em quinze tons e parecia protótipo.
- **Don't** usar controles nativos sem desenho (`select`, checkbox com `accent-color`, `title=` como tooltip) nem cortes secos ao abrir, fechar ou carregar.
- **Don't** colocar eyebrows em caixa alta com tracking acima de seções, cartões idênticos em grade como resposta padrão, gradiente em texto, vidro decorativo, "número gigante + rótulo" de SaaS.
- **Don't** usar bounce, elástico, coreografia de carregamento, parallax ou animação em ações de teclado; nada de UI acima de 300 ms fora da sheet (500 ms).
- **Don't** apresentar exemplos fictícios como ofertas reais nem usar linguagem de checkout ("comprar", "carrinho", "em estoque").
