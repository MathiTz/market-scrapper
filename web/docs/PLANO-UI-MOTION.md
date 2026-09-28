# Plano de evolução visual e de motion — Mercado em Dia

27/09/2026. Base: branch local `ux/auditoria-experiencia` (a partir de `main` @ `12e46d0`), depois da
auditoria de UX registrada em [AUDITORIA-UX.md](AUDITORIA-UX.md). Este plano trata do que a auditoria não
cobriu: a interface ainda parece um protótipo. Controles no estilo padrão do navegador, tooltips nativos,
fonte de sistema, fundos verdes, e tudo abre, fecha e carrega em corte seco.

Objetivo: sair do wireframe para um produto com sistema de design próprio, componentes com todos os estados
e movimento que explica abertura, fechamento e carregamento, sem virar um site de marketing. O fundo deixa
de ser verde: branco ou branco com 3% de "gelo".

## Referências usadas e como cada uma entra

| Referência | O que foi tirado dela | Onde aparece neste plano |
|---|---|---|
| [emilkowalski/skills](https://github.com/emilkowalski/skills) (animate, find-animation-opportunities, improve-animations, review-animations, mobile-native, pick-ui-library) | O portão de decisão (frequência → propósito → ferramenta → propriedades → curva e duração → interrupção → reduced motion), as curvas e durações exatas, o formato de plano executável, a lista de bibliotecas (Base UI, Sonner, motion, NumberFlow) | Seções 7 e 8; pasta `plans/` |
| [impeccable.style](https://impeccable.style) (skill `impeccable` instalada: `product.md`, `animate.md`, `typeset.md`, `document.md`) | Registro **product** (design serve à tarefa), estratégia de cor "Restrained", escala de tipo fixa em rem com razão 1,125–1,2, uma família só, grade de estados por componente, skeletons em vez de spinners, banimentos (eyebrow em toda seção, cartões idênticos, gradiente em texto, vidro), formato de `DESIGN.md` (Stitch) | Seções 2, 4, 5, 6; `PRODUCT.md` criado; `DESIGN.md` no fim da fase 0 |
| [appariciojunior/PrismSystem](https://github.com/appariciojunior/PrismSystem) | Arquitetura de tokens em três camadas (fundação → paleta → semântica), nomes semânticos (`surface-canvas`, `surface-level-1`, `text-primary`, `border-primary`, `interactive-primary-fill-default/hover/pressed`, `messaging-*`, `elevation-*`), rampas em OKLCH, anel de foco resolvido até ≥ 3:1, bateria de checagens (contraste, tokens sem literais), grade de estados obrigatória, "só tokens semânticos, nunca hex solto", regra "flag, never guess" | Seção 3; scripts `tokens/build` e `tokens/check`; `plans/000` |
| [appariciojunior/website-audit-skill](https://github.com/appariciojunior/website-audit-skill) | Camadas de auditoria (conteúdo, estrutura, visual, técnica), marcadores 🔴🟡🟢, tabela de ação priorizada, checagem de dialeto PT-BR | Seção 9 e tabela final |
| [appariciojunior/motion-studio](https://github.com/appariciojunior/motion-studio) | Catálogo de efeitos com parâmetros: skeleton (wave/pulse), shimmer, spinner, dots, toast empilhado, drawer iOS (curva 0,32/0,72/0/1, flick por velocidade, fundo que recua), modal, popover, tooltip com grupo instantâneo, smooth tabs (pílula que desliza), page transitions com "blur bridge", stagger list, sliding number, copy button (morph de ícone), accordion, swipe actions, hold-to-confirm | Seção 7 (cada momento cita o efeito de origem e os parâmetros) |

Conflitos entre referências foram resolvidos a favor de Emil Kowalski para valores de motion (curvas,
durações, o que não animar) e de impeccable/PrismSystem para sistema e tokens. Do motion-studio entram os
padrões, não a biblioteca inteira: cada efeito escolhido passa pelo portão de frequência e propósito.

## 1. Diagnóstico: por que parece protótipo

Medições em `app/globals.css` e `components/` (branch atual):

| Sintoma | Evidência | Efeito |
|---|---|---|
| Sem escala tipográfica | 26 tamanhos distintos de fonte (9 a 44 px; 67 usos de 12 px, 43 de 13, 49 de 14, 10 de 15, 8 de 16) | hierarquia "lamacenta": 12/13/14/15/16 convivem sem papel definido |
| Fonte invisível | `font-family: Arial, Helvetica, sans-serif`; títulos com `letter-spacing: -1.8px` num Arial | lê-se como wireframe; números de preço sem personalidade e sem alinhamento tabular |
| Sem escala de espaço e raio | 40 valores distintos de padding (1 a 160 px, incluindo 7, 9, 11, 13, 17, 19, 21, 23, 29 px); 17 raios distintos (3 a 32 px + 999) | nada "encaixa"; cartão, botão e campo têm cantos diferentes |
| Cor sem sistema | 84 literais hex; 10 tokens em `:root`; `--bg #f6f8f7` e mais de 15 tons de verde-claro usados como fundo de painéis, avisos, seleções e cartões | tudo verde; a marca vira ruído e some como acento |
| Controles nativos | 5 `<select>` no público (ordenar, desconto, mês e semana dos encartes, região), checkboxes com `accent-color`, 3 `<details>`, tooltips por `title=` (`nearby-filter.tsx:227`, `offer-share.tsx:99`), barra de rolagem padrão na faixa de ofertas | estilo do navegador, diferente em cada sistema |
| Corte seco | 4 diálogos nativos abrem com `showModal()` e fecham desmontando (`store-location.tsx:43-45`, `product-range-card.tsx:114-116`, `flyer-stories.tsx:66-68`, `nearby-filter.tsx:75`); backdrop sem transição; toast (`market.tsx:1826`) aparece e some sem transição; troca de vista e abertura do produto por troca de DOM + `scrollTo` | cada ação parece um "flash" |
| Carregamento sem forma | caixas de texto "Carregando as ofertas publicadas…", "Carregando a cobertura…", "Carregando encartes…", "Filtrando…" (`market.tsx:1170, 1256, 1286, 1470`); só uma animação `pulse`; fotos aparecem de repente ao carregar; a busca troca a grade inteira por um bloco de texto (salto de layout) | a página "pisca" enquanto trabalha |
| Motion inexistente | 4 regras de `transition` (todas de cor, adicionadas na última rodada) e 2 `@keyframes` (`pulse`, spinner) em 3.100 linhas; nenhum `:active` com escala; `prefers-reduced-motion` mata **tudo** (`animation: none; transition: none`) em vez de reduzir | nenhum retorno físico ao toque; quem prefere menos movimento perde até o fade |
| Elevação sem vocabulário | 6 `box-shadow` avulsos; z-index 10/20/30 sem escala | cartão, diálogo e toast não têm profundidade coerente |
| Cartões em tudo | grade de cartões brancos idênticos sobre fundo tingido, em todas as vistas | o padrão "cartão como resposta padrão" que impeccable classifica como preguiçoso |

O que já está bom e fica: identidade do wordmark (`mercado em dia.`), ícones lucide, navegação de quatro
abas, estados de erro/offline/vazio da auditoria, textos com escopo ("Único preço", "Subtotal parcial"),
leitor de encartes com pausa e teclado, diálogos nativos com devolução de foco.

## 2. Direção

- **Registro:** product. O design serve à tarefa; familiaridade é virtude; delight só em momentos raros.
- **Cena:** "Uma pessoa no celular, na cozinha, com a lista na cabeça, decide em um minuto se vale ir ao
  Atacadão ou ficar no mercadinho da esquina." Luz ambiente, uma mão. Isso força tema claro, alto contraste,
  alvos grandes, movimento curto.
- **Estratégia de cor:** Restrained. Neutros frios quase brancos + um acento (o verde da marca `#116249`,
  preservado) em ≤ 10% da tela: botão primário, seleção, marca. Âmbar só para condição e alerta; lima só para
  desconto informado pela loja. Nenhuma superfície verde.
- **Fundo:** `--surface-canvas` = branco com 3% de gelo, `oklch(98.8% 0.003 240)` ≈ `#f9fbfd`. Cartões e
  painéis em branco puro com fio de 1 px (`--border-subtle`). Alternativa aprovada: canvas `#ffffff` com
  painéis em `oklch(96.5% 0.005 240)` ≈ `#f1f4f6`.
- **Âncoras nomeadas:** a etiqueta de gôndola (número domina, unidade pequena e alinhada), o app do iOS
  Ajustes (listas com fio, controles desenhados, sheets que sobem), o Linear no desktop (densidade, estados
  de hover e foco em tudo, motion de 150–250 ms sem coreografia).
- **Anti-referências:** as de `PRODUCT.md`: checkout, landing de SaaS, vidro decorativo, eyebrows em toda
  seção, motion decorativa.

Teste de reflexo: "comparador de preços → verde e cartões" era o reflexo de primeira ordem e é exatamente o
estado atual. A saída não é "editorial com serifa", que seria o reflexo de segunda ordem; é uma UI de
utilidade com tipografia de etiqueta de preço e movimento de app nativo.

## 3. Sistema de design (método PrismSystem, dimensionado para este repositório)

### 3.1 Arquitetura

```
web/tokens/tokens.json        fonte única (três camadas)
web/tokens/build.mjs          gera app/tokens.css (variáveis CSS) e tokens.d.ts
web/tokens/check.mjs          contraste de cada par texto/fundo semântico; literais hex fora de tokens.css
app/globals.css               só consome var(--…); zero hex depois da fase 1
DESIGN.md + .impeccable/design.json   documentação gerada (formato Stitch) ao fim da fase 0
```

Camadas, na regra do PrismSystem: **semântico referencia paleta, nunca fundação**; nada no CSS referencia
fundação ou paleta diretamente. O PrismSystem gera as rampas com seu Controller (Node, `npm run controller`);
aqui as rampas são declaradas em OKLCH no `tokens.json` e o `build.mjs` resolve para hex sRGB com mapeamento
de gamut, o mesmo resultado sem carregar o monorepo. Escala: cerca de 130 tokens (o Prism tem 2.748 porque
cobre iOS, dark e gráficos; nada disso é necessário agora).

### 3.2 Fundação e paleta (OKLCH; hex resolvido pelo build)

| Rampa | Passos | Notas |
|---|---|---|
| `neutral` (gelo) | 0 `#fff` · 50 `98.8% 0.003 240` · 100 `96.5% 0.005 240` · 200 `92% 0.008 240` · 300 `86% 0.01 240` · 400 `70% 0.015 235` · 500 `55% 0.02 230` · 600 `45% 0.02 230` · 700 `35% 0.02 230` · 800 `28% 0.015 230` · 900 `22% 0.015 230` | tinta fria mínima (chroma 0,003–0,02): o "gelo seco"; nenhum passo verde |
| `brand` (verde) | 50 `97% 0.02 163` · 100 `94% 0.045 163` · 200 `88% 0.08 163` · 300 `78% 0.11 163` · 400 `62% 0.12 163` · 500 `50% 0.11 163` · **600 = `#116249`** · 700 `36% 0.085 163` · 800 `30% 0.07 163` · 900 = `#173d30` | 600 e 900 são os valores atuais da marca, preservados |
| `amber` (condição/alerta) | 50 `96% 0.04 80` · 100 `92% 0.07 80` · 600 `45% 0.1 70` · 700 `38% 0.09 70` | substitui `#fff2d6/#825619/#865510` |
| `lime` (desconto) | 100 `92% 0.14 120` · 900 `30% 0.08 130` | substitui `#d9ed92/#173d30` no selo "20% OFF" |
| `red` (erro/destrutivo) | 50 `96% 0.02 25` · 600 `50% 0.18 25` · 700 `42% 0.16 25` | substitui `#a3372b/#c0392b/#fbeceb` |
| `blue` (informativo) | 50 `96% 0.02 250` · 700 `40% 0.12 255` | substitui `#e3eefc/#1d4f91` ("Mais perto") |

### 3.3 Tokens semânticos (nomes no padrão Prism, prefixo `--md-`)

| Grupo | Tokens | Valor inicial |
|---|---|---|
| Superfície | `surface-canvas`, `surface-level-1` (cartão, diálogo), `surface-level-2` (painel, campo), `surface-inverse` (toast, barra do leitor) | neutral-50, neutral-0, neutral-100, neutral-900 |
| Texto | `text-primary`, `text-secondary`, `text-tertiary` (só ≥ 18 px ou decorativo), `text-inverse`, `text-brand`, `text-warning`, `text-error`, `text-link` | neutral-900, neutral-600, neutral-500, neutral-0, brand-700, amber-700, red-700, brand-700 |
| Borda | `border-subtle` (fio de cartão), `border-default` (campo), `border-strong` (campo em hover), `border-selected` | neutral-200, neutral-300, neutral-400, brand-600 |
| Interativo primário | `interactive-primary-fill-default/hover/pressed`, `interactive-primary-text` | brand-600, brand-700, brand-800, neutral-0 |
| Interativo secundário | `-secondary-fill-default/hover/pressed`, `-secondary-border`, `-secondary-text` | neutral-0, neutral-100, neutral-200, neutral-300, neutral-900 |
| Interativo fantasma | `-ghost-fill-hover/pressed`, `-ghost-text` | neutral-100, neutral-200, brand-700 |
| Interativo destrutivo | `-negative-fill-hover`, `-negative-text` | red-50, red-700 |
| Seleção | `selected-fill`, `selected-border`, `selected-text` | brand-50, brand-600, brand-800 |
| Desabilitado | `disabled-fill`, `disabled-text` | neutral-100, neutral-500 |
| Foco | `focus-ring` (≥ 3:1 sobre canvas, cartão e painel; o check falha se não) | brand-900 |
| Mensagens | `messaging-{info,success,warning,error}-{fill,border,text}` | blue/brand/amber/red 50 · 100/200 · 700 |
| Preço | `price-ink`, `price-unit`, `price-regular` (riscado), `deal-fill`, `deal-text`, `condition-fill`, `condition-text` | neutral-900, neutral-600, neutral-500, lime-100, lime-900, amber-50, amber-700 |
| Elevação | `elevation-0` (nenhuma), `elevation-1` (hover: `0 1px 2px oklch(22% .015 230 / 6%), 0 8px 24px … / 6%`), `elevation-2` (popover, tooltip), `elevation-3` (diálogo, sheet), `elevation-inverse` (toast) | sombras tingidas com a tinta, nunca preto puro |
| Raio | `radius-xs 6` (chip, selo), `radius-sm 10` (botão, campo), `radius-md 14` (cartão), `radius-lg 20` (diálogo, sheet), `radius-pill 999` | 5 valores no lugar de 17 |
| Espaço | `space-1 4` · `2 8` · `3 12` · `4 16` · `5 20` · `6 24` · `8 32` · `10 40` · `12 48` · `16 64` | base 4; ritmo vertical em múltiplos de 24 (linha de 16 × 1,5) |
| Tipo | ver seção 4 | |
| Motion | ver seção 7.1 | |
| Camadas | `z-dropdown 10` · `z-sticky 20` · `z-dock 30` · `z-backdrop 40` · `z-modal 50` · `z-toast 60` · `z-tooltip 70` | substitui 10/20/30 avulsos |
| Grade | `content-max 1100`, `gutter 16/32`, breakpoints 460 / 760 / 1024 / 1200 | os atuais, nomeados |

### 3.4 Checagens (a "bateria" do Prism, em dois scripts)

- `node tokens/check.mjs contrast`: calcula WCAG para cada par declarado em `tokens.json > pairs`
  (`text-primary` sobre `surface-canvas`, `interactive-primary-text` sobre `-fill-hover`, `focus-ring`
  sobre canvas/level-1/level-2…). Falha < 4,5:1 para texto e < 3:1 para foco, ícone e borda de campo.
- `node tokens/check.mjs literals`: falha se `app/globals.css` ou `components/**` contiver hex, `rgb(`,
  `oklch(` ou `px` de raio/espaço fora da escala. Roda no `npm run build` (script `prebuild`).
- Exceções declaradas em `tokens/allow.json` (ex.: cor de marca no `manifest.webmanifest`).

### 3.5 Documentação gerada

Ao fim da fase 0, `/impeccable document` gera `DESIGN.md` (frontmatter Stitch: colors, typography, rounded,
spacing, components) e `.impeccable/design.json` (rampas, sombras, motion, snippets de componentes), a
partir de `tokens.css` e dos componentes. `VISUAL.md` passa a apontar para eles.

## 4. Tipografia

### 4.1 Família

Recomendada: **Archivo** (variável, peso 100–900 e **largura 62–125%**), auto-hospedada via
`@fontsource-variable/archivo` 5.3.0 (só o arquivo `wdth`, subconjuntos latin e latin-ext, ~150 kB woff2).

Por quê: é uma grotesca de origem tipográfica brasileira (Omnibus-Type, 2012) com DNA de sinalização e
etiqueta; o eixo de largura permite **preços semicondensados (wdth 88–92, peso 700)** como nos encartes,
sem uma segunda família. Não está na lista de reflexos saturados (Inter, DM Sans, Plus Jakarta, Instrument,
Space Grotesk, IBM Plex, Outfit). Verificar `tnum` no Wakamai Fondue antes da fase 0; se faltar, os preços
usam `font-variant-numeric: tabular-nums` com fallback para Golos Text.

Alternativas (uma família, mesma escala): **Golos Text** (grotesca de interface com numerais excelentes e
`tnum`, mais neutra) e **Hanken Grotesk** (humanista, mais quente). Ficam registradas como decisão a confirmar.

Carregamento: `@font-face` com `font-display: swap` e fallback com métricas ajustadas
(`size-adjust`/`ascent-override` para Arial) para eliminar salto de layout; preload do arquivo latin.

### 4.2 Escala (fixa em rem, razão ≈ 1,2, registro product)

| Token | Tamanho | Uso | Peso · entrelinha · tracking |
|---|---|---|---|
| `text-xs` | 0,75 rem (12) | horário, origem, notas de rodapé | 400 · 1,45 · 0 |
| `text-sm` | 0,8125 rem (13) | metadados de cartão, rótulos de filtro | 400/500 · 1,45 · 0 |
| `text-md` | 0,875 rem (14) | UI secundária, botões pequenos, chips | 500 · 1,4 · 0 |
| `text-base` | 1 rem (16) | corpo, campos, botões | 400/600 · 1,5 · 0 |
| `text-lg` | 1,125 rem (18) | nome do produto no cartão, h3 | 600 · 1,3 · −0,005em |
| `text-xl` | 1,25 rem (20) | h2 de seção | 650 · 1,25 · −0,01em |
| `text-2xl` | 1,5 rem (24) | h1 de vista no mobile | 700 · 1,2 · −0,015em |
| `text-3xl` | 1,75 rem (28) | h1 no desktop, preço no cartão | 700 · 1,15 · −0,02em |
| `text-4xl` | 2,125 rem (34) | preço no detalhe | 700 · 1,05 · −0,02em |

Regras: nenhum texto de decisão abaixo de 12 px (já garantido pela auditoria); corpo em 16; `text-wrap:
balance` em h1–h3; `text-wrap: pretty` em parágrafos; medida máxima 65ch em prosa.

### 4.3 O preço como assinatura

`.price`: `font-variation-settings: "wdth" 90`, peso 700, `tabular-nums`, `text-3xl` no cartão e
`text-4xl` no detalhe, tinta `price-ink` (não verde). A unidade (`/kg`, `/L`) em `text-sm` `price-unit`
alinhada na base. O preço riscado em `price-regular` com `text-decoration-thickness: 1.5px`. O selo de
desconto em `lime` com `text-xs` 700. É a única licença tipográfica do sistema; o resto é largura 100.

### 4.4 O que sai

- Eyebrows em caixa alta com tracking em toda seção ("SUAS COMPRAS EM FORTALEZA", "DIRETO DOS
  SUPERMERCADOS", "SEM CADASTRO, NO SEU DISPOSITIVO", "ONDE ENCONTRAR", "LOJAS MAIS PRÓXIMAS", "TAMANHOS
  DIFERENTES"): viram frase em caixa normal `text-sm text-secondary` ou somem. Permanece um só kicker de
  marca, se algum.
- `letter-spacing: -1.8px` em títulos: tracking passa a ser por token e nunca abaixo de −0,02em.

## 5. Superfícies, elevação e layout

- Canvas gelo; cartões brancos com `border-subtle`; em hover `elevation-1` + `border-default`; nenhum fundo
  verde. Seleção usa `selected-fill` (brand-50) apenas no elemento selecionado.
- Painéis (filtros, "Como ler os preços", estimativas): `surface-level-2` sem borda, raio `md`. Cartão
  dentro de painel é proibido (cartão aninhado).
- Menos cartões: a lista "Minha lista" e as linhas da comparação passam a ser listas com fio
  (`border-subtle` entre itens) num único contêiner, no estilo Ajustes do iOS; os cartões ficam nos
  resultados e na faixa Hoje, onde o formato é o produto.
- Cabeçalho e dock do mobile: brancos, fio de 1 px, opacos (sem vidro).
- Ritmo: seções separadas por `space-8/10`, grupos internos por `space-3/4`; nada de 11, 13, 17, 19 px.
- Desktop ≥ 1024: comparação em tabela compacta de duas colunas (rede/condição | preço/ações), já no
  backlog da auditoria (P2-16); resultados em 3 colunas com `repeat(auto-fill, minmax(280px, 1fr))`.

## 6. Vocabulário de componentes e grade de estados

Cada componente entrega os estados da grade do Prism e do impeccable: **default, hover, focus-visible,
active (pressionado), selected, disabled, loading, error/invalid**, mais empty onde couber. Nenhum componente
sobe sem a grade completa; a story de estados é um bloco no `/demo` (rota `/demo?vitrine=1`), que serve de
"Components sheet" do Prism para conferir hover, foco, pressionado e carregamento lado a lado.

| Componente | Hoje | Alvo | Biblioteca |
|---|---|---|---|
| Botão primário/secundário/fantasma/destrutivo, tamanhos sm/md/lg | `.primary/.secondary/.text-link`, alturas 44/46/48 misturadas | uma `Button` com `variant` e `size`; `:active` `scale(.97)` 160 ms; `loading` com spinner inline de 16 px e rótulo mantido; `disabled` sem hover | CSS próprio |
| Campo de texto, busca | `.searchbar` com foco herdado | borda `border-default` → `border-strong` em hover → anel `focus-ring`; botão limpar; indicador de atividade (spinner 14 px) enquanto filtra | CSS próprio |
| Select (ordenar, desconto, mês/semana) | `<select>` nativo | `Select` do Base UI: gatilho no estilo do campo, lista em popover com origem no gatilho, `scale(.95)→1` 180 ms; teclado e leitor de tela nativos do primitivo | `@base-ui-components/react` |
| Checkbox e rádio (condições, sem preço, raio) | `accent-color` | caixa desenhada 20 px, marca em SVG com traço que se desenha (`stroke-dashoffset`, 160 ms); rádio de raio vira **segmented control** com pílula que desliza 180 ms | Base UI Checkbox; CSS |
| Chips (categorias, redes, filtros ativos) | `.category-row button`, `.chip-check`, `.filter-chip` | um `Chip` com `selected`, ícone ✓ que entra por crossfade 120 ms, `:active` .97 | CSS |
| Tooltip | `title=` nativo | `Tooltip` do Base UI: 125 ms `scale(.97)→1` com `transform-origin` no gatilho, atraso 400 ms, **instantâneo entre vizinhos** (padrão Emil / motion-studio tooltip group); só para rótulos de ícones, nunca para condição de preço | Base UI |
| Diálogo (Onde encontrar, tamanhos, leitor) | `<dialog>` nativo, abre/fecha em corte | `<dialog>` nativo mantido (foco e Esc já corretos) + entrada `scale(.96)→1` + opacidade 250 ms `ease-out`, saída 190 ms, backdrop em fade sincronizado (`@starting-style` + `transition-behavior: allow-discrete`) | CSS nativo |
| Bottom sheet (Perto de você, Onde encontrar, tamanhos no mobile) | diálogo centrado | no mobile (< 760 px) o mesmo `<dialog>` vira sheet: sobe de `translateY(100%)` em 500 ms com a curva iOS `cubic-bezier(.32,.72,0,1)`, alça de arrasto, dismiss por arrasto ou flick (velocidade), fundo recua `scale(.96)` (motion-studio `drawer`) | `motion` (drag + spring) |
| Toast | `div.toast` sem transição, 3,2 s | Sonner headless com nossos tokens: entra de baixo (`translateY(100%)` 400 ms `ease`), empilha, pausa em hover, arrasto para dispensar, ação **Desfazer** na remoção; no mobile acima do dock | `sonner` |
| Skeleton | não existe | `Skeleton` com onda por `::after` em `translateX` (só transform), 1,5 s linear, cores `neutral-100/200`; variantes: cartão, faixa (4 cartões), detalhe, linha de lista, encarte | CSS |
| Foto de produto | aparece de repente | skeleton por baixo; `img` entra com opacidade 0→1 em 200 ms ao carregar; falha mantém o fallback | CSS |
| Faixa Hoje (offer rail) | scroll-snap nativo, barra visível | scroll-snap mantido (toque, teclado, acessibilidade); barra oculta com ponteiro fino; máscara de desvanecimento nas bordas; setas com `scrollBy` suave; entrada escalonada 40 ms × 6 cartões só na primeira carga | CSS |
| Abas Hoje/Buscar/Encartes/Lista | troca de classe | pílula de seleção que desliza 180 ms `ease-in-out` (medida por JS + `transform`), conteúdo em crossfade 150 ms; no mobile o indicador de 3 px desliza igual | CSS + JS mínimo |
| Vista → detalhe do produto | troca de DOM | **momento assinatura:** a foto do cartão cresce até o herói do detalhe (View Transitions API, `view-transition-name` por produto), 250 ms `ease-out`; o resto em crossfade; volta é o inverso; navegadores sem suporte trocam instantâneo | nativo |
| Quantidade, totais | texto trocado | dígitos deslizam (NumberFlow) 300 ms nos totais da estimativa e na quantidade | `@number-flow/react` |
| Adicionar à lista | `+` vira `✓ n` de repente | conteúdo do botão em crossfade com `blur(2px)` 200 ms (motion-studio `copy-button`), botão `.97` no press, contador do dock "pulsa" `scale(.6)→1` 220 ms uma vez (WAAPI, cancela a anterior) | CSS + WAAPI |
| Remover da lista | some de repente | linha colapsa (`grid-template-rows 1fr→0fr` + opacidade, 200 ms) e o toast oferece Desfazer; no mobile, arrastar para a esquerda revela "Remover" (motion-studio `swipe-actions`) na fase 4 | CSS; `motion` |
| `<details>` (estimativas, preços fora da comparação) | abre em corte | conteúdo em `grid-template-rows 0fr→1fr` 200 ms `ease-out`, seta gira 180° | CSS |
| Barra de progresso do leitor de encartes | ok | mantida; troca de página em crossfade 150 ms; zoom por `transform` 200 ms | CSS |
| Estado vazio / erro / offline | `StatusPanel` estático | entra com `opacity` + `translateY(8px)` 250 ms; ícone sem animação contínua | CSS |

## 7. Motion

### 7.1 Tokens (os valores de Emil, sem aproximação)

```css
--ease-out:    cubic-bezier(0.23, 1, 0.32, 1);   /* entradas e saídas de UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);  /* movimento de algo já na tela (pílula, zoom) */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);   /* sheet iOS */
--ease:        ease;                             /* hover e cor */
--dur-press: 160ms; --dur-tooltip: 125ms; --dur-menu: 180ms; --dur-state: 200ms;
--dur-modal: 250ms; --dur-modal-exit: 190ms; --dur-sheet: 500ms; --dur-toast: 400ms;
--motion-scale-in: 0.96; --motion-lift: 8px;    /* zerados em reduced motion */
```

Springs (só em gesto): `{ type: "spring", duration: 0.5, bounce: 0.2 }`; bounce nunca acima de 0,3 e nunca
em diálogos, botões ou listas.

### 7.2 Catálogo por momento (portão: frequência → propósito → ferramenta → receita)

| # | Momento | Hoje | Frequência | Propósito | Receita exata | Origem |
|---|---|---|---|---|---|---|
| 1 | Abrir/fechar diálogo | corte | ocasional | evitar salto | `opacity 0→1`, `scale(.96)→1`, 250 ms `--ease-out`; saída 190 ms; backdrop `opacity` sincronizado; `transform-origin: center` (modal é exceção) | Emil RECIPES "Modal"; motion-studio `modals` |
| 2 | Sheet no mobile | diálogo centrado | ocasional | consistência espacial (vem de baixo, volta para baixo) | `translateY(100%)→0` 500 ms `--ease-drawer`; arrasto com captura de ponteiro; dismiss por distância ≥ 40% **ou** velocidade > 0,11 px/ms; amortecimento ao passar do topo; fundo `scale(.96)` e canto 12 px | Emil "Drawer", "Drag to dismiss"; motion-studio `drawer` |
| 3 | Toast | corte, some em 3,2 s | ocasional | consistência espacial + retorno | Sonner: entra de baixo 400 ms `ease` (a personalidade do toast é um pouco mais lenta), sai pelo mesmo lado; transições, não keyframes (empilha sem reiniciar) | Emil RECIPES "Toast"; ask-sonner |
| 4 | Carregar snapshot | texto pulsando | primeira carga | indicar estado | skeleton da faixa (4 cartões), da cobertura e dos 3 encartes; onda 1,5 s linear em `::after translateX(-100%→100%)`; conteúdo real entra por crossfade 200 ms; texto "Carregando…" fica só para leitor de tela | motion-studio `skeleton` (wave), impeccable "skeleton, não spinner" |
| 5 | Filtrar/buscar | grade some, "Filtrando…" | dezenas/dia | evitar salto | grade atual permanece com `filter: blur(2px); opacity:.7` 200 ms enquanto recalcula; contagem "Atualizando…"; **sem** stagger a cada tecla | Emil "blur bridge"; find-animation-opportunities (rejeita stagger frequente) |
| 6 | Foto carregada | pop | por cartão | evitar salto | `opacity 0→1` 200 ms `--ease-out` sobre skeleton; sem transform | — |
| 7 | Abrir produto | troca + scrollTo | ocasional | **consistência espacial (assinatura)** | `document.startViewTransition`; `::view-transition-group(product-photo)` 250 ms `--ease-out`; `old/new(root)` crossfade 150 ms; volta inverte; sem suporte: instantâneo | motion-studio `modal-shared-layout`, `page-transitions`; impeccable "shared element" |
| 8 | Trocar de aba | troca de classe | ~10/dia | indicar estado | pílula `transform` 180 ms `--ease-in-out`; conteúdo crossfade 150 ms (View Transition `root`), sem deslocamento; teclado (Tab/Enter) igual, sem animação extra | motion-studio `smooth-tabs`; Emil "tab indicator" |
| 9 | Pressionar qualquer botão | só cor | dezenas/dia | retorno | `:active { transform: scale(.97) }` `transition: transform 160ms var(--ease-out)`; em toque também | Emil "Button press" |
| 10 | Hover | cor 120 ms | dezenas/dia | retorno | mantido, gateado por `(hover: hover) and (pointer: fine)`; cartão sobe para `elevation-1` sem `translateY` | Emil "hover gating" |
| 11 | Tooltip | nativo | dezenas/dia | rótulo | 125 ms `scale(.97)→1`, origem no gatilho, atraso 400 ms, vizinhos instantâneos (`[data-instant]`) | Emil RECIPES "Tooltip"; motion-studio `tooltip` |
| 12 | Select/popover | nativo | dezenas/dia | consistência espacial | 180 ms `scale(.95)→1` com `transform-origin: var(--transform-origin)` | Emil RECIPES "Dropdown"; motion-studio `popover` |
| 13 | Adicionar à lista | troca | ocasional | retorno + indicação de estado | conteúdo do botão crossfade `blur(2px)` 200 ms; contador do dock `scale(.6)→1` 220 ms via `el.animate()` (cancela se repetir) | motion-studio `copy-button`; Emil "blur to mask" |
| 14 | Remover da lista / desfazer | some | ocasional | evitar salto | linha `grid-template-rows 1fr→0fr` + `opacity` 200 ms; desfazer reinsere com o inverso | Emil RECIPES "Accordion"; motion-studio `accordion` |
| 15 | Totais e quantidade | troca | ocasional | indicação de estado | NumberFlow 300 ms `--ease-out`; `tabular-nums` | Emil pick-ui-library; motion-studio `sliding-number` |
| 16 | Faixa Hoje | scroll nativo | primeira carga | delight (raro) | entrada `opacity 0→1, translateY(8px)→0` 300 ms `--ease-out`, atraso 40 ms × índice, no máximo 6 cartões (240 ms); nunca ao filtrar; máscara nas bordas; setas `scrollBy` suave | Emil RECIPES "Stagger"; motion-studio `stagger-list` |
| 17 | Expandir estimativa | corte | ocasional | indicação de estado | `grid-template-rows 0fr→1fr` 200 ms, seta 180° | motion-studio `accordion` |
| 18 | Zoom do encarte | corte | ocasional | continuidade | `transform: scale()` 200 ms `--ease-in-out` a partir do centro do viewport | — |
| 19 | Estados vazio/erro | corte | raro | evitar salto | `opacity` + `translateY(8px)` 250 ms; sem loop | — |
| 20 | Conexão de volta | toast | raro | retorno | toast Sonner `success`; nada mais | — |

### 7.3 Rejeitados (o portão barrou)

- Coreografia de entrada na Hoje (fade-and-rise de cada seção): product loads into a task. **Rejeitado.**
- Stagger nos resultados a cada busca ou filtro: dezenas de vezes por dia. **Rejeitado**; só na primeira carga da faixa.
- Animar preços com contagem ("count-up") nos cartões: dado que a pessoa está lendo. **Rejeitado.**
- Scroll reveal, parallax, vidro no cabeçalho: marketing. **Rejeitado.**
- Bounce em diálogos, botões ou chips. **Rejeitado.**
- Animação em atalhos de teclado (Tab, Esc, Enter na busca): 100+/dia. **Rejeitado.**
- Cursor magnético, tilt de cartão, texto com shimmer (existem no motion-studio): decoração. **Rejeitados.**

### 7.4 Reduced motion e ponteiro

Substitui o `* { animation: none; transition: none }` atual:

```css
@media (prefers-reduced-motion: reduce) {
  :root { --motion-scale-in: 1; --motion-lift: 0px; --dur-sheet: 200ms; }
  .skeleton::after { animation: none; }          /* fica estático */
  ::view-transition-group(*) { animation-duration: 0.01ms; }
}
```

Fades de 120–250 ms permanecem (ajudam a compreender); deslocamentos e escalas viram 0; a sheet vira fade;
o leitor de encartes continua pausado por padrão. Hover só em `(hover: hover) and (pointer: fine)`;
`:active` em todo dispositivo.

### 7.5 Performance

`transform` e `opacity` apenas (exceções toleradas: `grid-template-rows` em colapso de 200 ms, `filter:
blur(2px)` em área pequena); nada de `transition: all`; `will-change` só durante o arrasto da sheet;
`contain: content` nos cartões; View Transitions limitadas ao herói do produto e ao crossfade de vista;
medição com o Performance panel a 4× CPU: diálogo, sheet, faixa e busca sem frames > 16 ms em sequência.

## 8. Mobile com cara de app (Emil `mobile-native` + motion-studio `drawer`)

- `-webkit-tap-highlight-color: transparent` (já existe) + `:active` visível em tudo.
- Hover "preso" após toque: eliminado pelo gate de ponteiro.
- `100dvh` e `env(safe-area-inset-bottom)` no dock e nas sheets (dock já usa safe-area).
- Campos com `font-size ≥ 16px` para o iOS não dar zoom (busca já em 16; conferir filtros e lista).
- `overscroll-behavior: contain` nas sheets e no leitor.
- Sheets em vez de modais centrados; arrasto com captura de ponteiro; proteção multi-toque.
- Barra de busca do dock: fica; ganha o botão limpar e o indicador de atividade.

## 9. Conteúdo e técnica (camadas do website-audit-skill)

Dialeto PT-BR consistente (sem "ligação", "equipa", "objectivo"); terminologia consistente ("preço do site",
"unidade", "rede", "referência") já revisada na auditoria. Pendências:

- 🟡 `index.html` sem `og:title`, `og:description`, `og:image` e `twitter:card`: um link compartilhado no
  WhatsApp aparece sem prévia. Adicionar com imagem 1200×630 estática.
- 🟡 Selo "Piloto em validação · Informação com origem" na busca do desktop: afirmação de processo sem
  explicação; mover o conteúdo para "Como ler os preços" e remover o selo.
- 🟢 Rodapé sem link para "Como ler os preços" nas outras vistas (só na Hoje).
- 🟢 `manifest.webmanifest` sem `screenshots` e `description`; ícone só SVG (sem PNG 192/512 para Android).
- 🟢 `alt` das fotos de produto: decorativas (`alt=""`) no cartão, "Foto de …" no herói: correto; manter.

## 10. Fases, esforço e dependências

| Fase | Entrega | Esforço | Depende de |
|---|---|---|---|
| **0 · Fundação** (`plans/000`, `001`, `002`) | `tokens.json` + build + check; `tokens.css`; canvas gelo e fim dos fundos verdes; Archivo; escala de tipo; tokens de motion; nova política de reduced motion; `DESIGN.md` gerado | 2 dias | decisão da fonte |
| **1 · Vocabulário** (`plans/003`, `007`, `009`) | Button/Field/Chip/Checkbox/Segmented; Select e Tooltip com Base UI; grade de estados; vitrine em `/demo?vitrine=1`; hover + press em tudo; sem hex no CSS (check passa) | 3 dias | fase 0 |
| **2 · Estados em movimento** (`plans/003`, `004`, `005`) | diálogos com entrada/saída; skeletons e fade de fotos; busca sem salto; Sonner com Desfazer; `<details>` animado; adicionar/remover com transição; NumberFlow nos totais | 2 dias | fase 1 |
| **3 · Navegação** (`plans/006`) | View Transitions: herói do produto e crossfade de vista; pílula das abas; faixa com máscara, setas e entrada única | 1–2 dias | fase 2 |
| **4 · App no celular** (`plans/008`) | sheets com arrasto e flick; swipe para remover; ajustes mobile-native | 2–3 dias | fase 3; `motion` |
| **5 · Polimento e auditoria** | `/impeccable audit` + `polish`; checklist `review-animations` (tabela Before/After); Lighthouse; capturas antes/depois com o roteiro da auditoria; teste em aparelho real (gestos) | 1–2 dias | tudo |

Dependências novas (versões verificadas em 27/09/2026): `@fontsource-variable/archivo` 5.3.0,
`@base-ui-components/react` 1.0.0-rc.0 (release candidate: risco baixo, API estável; alternativa
`radix-ui` 1.4), `sonner` 2.0.8, `@number-flow/react` 0.6.2, `motion` 13.4.4 (só fase 4; importar de
`motion/react` e usar a string `transform` completa, não `x/y`, nos elementos sob carga). Orçamento de
bundle: de 142 kB gz para no máximo 185 kB gz no fim da fase 4; fontes fora do orçamento de JS.

Riscos: Base UI em rc (mitigação: encapsular em `components/ui/*` para trocar por Radix se preciso); View
Transitions sem suporte em navegadores antigos (progressivo: instantâneo); Archivo sem `tnum` (fallback
Golos Text); regressão de acessibilidade ao trocar `<select>` (mitigação: Base UI e testes de teclado no
roteiro de fluxos).

## 11. Validação e aceite

- `npm run typecheck`, `npm test`, `npm run build` verdes; `node tokens/check.mjs` sem falhas.
- Roteiro de capturas e fluxos da auditoria (`referencias/auditoria-ux/scripts`) reexecutado: 0 px de
  rolagem horizontal, 62/62 fluxos, mais 6 fluxos novos (abrir/fechar diálogo, sheet por arrasto, desfazer
  pelo toast, busca sem salto, herói do produto, reduced motion).
- `hover-audit`: 100% dos controles com hover em ponteiro fino e `:active` em toque; estados selecionados
  sem hover (por desenho).
- Contraste: todos os pares do `tokens.json` ≥ 4,5:1 (texto) e ≥ 3:1 (foco, ícone, borda de campo).
- Motion (checklist `review-animations`): nenhum `transition: all`, nenhum `scale(0)`, nenhum `ease-in`,
  nenhuma UI > 300 ms (sheet 500 ms é a exceção documentada), popovers com origem no gatilho, keyframes só
  em skeleton e spinner, hover gateado, reduced motion com fade e sem deslocamento.
- Performance: Lighthouse mobile ≥ 90; sem frames longos em sequência a 4× CPU nos quatro cenários da 7.5.
- Antes/depois em 320, 390, 768 e 1280 px, mesmas cenas da auditoria, com o mesmo snapshot congelado.

## 12. Decisões tomadas (27/09/2026, com o proprietário)

1. Fonte: **Archivo** (variável, eixo de largura), auto-hospedada.
2. Dependências: **completo** (Base UI + Sonner + NumberFlow, e `motion` só na fase 4).
3. Canvas: `#f9fbfd` (gelo 3%), cartões brancos com fio; alternativa `#ffffff` fica registrada.
4. Execução: **fase 0 concluída nesta branch** (`ux/auditoria-experiencia`); ver `plans/README.md` para o
   status e `VALIDACAO.md` para os resultados.
5. 28/09: **fases 1 a 4 concluídas** na mesma branch, na ordem 009 → 007 → 003 → 004 → 005 → 006 → 008, com
   estes desvios do texto dos planos, todos deliberados:
   - Botão em `loading` mantém o rótulo visível e põe o spinner no lugar do ícone (o texto "Obtendo
     localização…" informa a etapa); o truque de `color: transparent` do plano 009 não foi usado.
   - `.primary` e `.secondary` continuam como aliases de `.btn` porque `components/admin.tsx` (fora do escopo
     público) os usa; nenhum componente público os referencia.
   - A checkbox é um `<input>` nativo desenhado por CSS (`:has(:checked)`), não Base UI: associação de rótulo,
     teclado e leitor de tela vêm de graça e não há risco de mudança de API. Base UI ficou no select e no tooltip.
   - O `Toaster` do Sonner é montado dentro de `Market` (um só), para o deslocamento acompanhar o dock com ou
     sem barra de busca; o diálogo de tamanhos fecha antes de notificar (o toast fica fora da top layer).
   - `searching` deixou de ser estado: é `query.trim() !== search.trim()`; o antigo efeito o zerava no mesmo
     ciclo em que era ligado, de modo que o "Filtrando…" nunca chegava a aparecer.
   - `@starting-style` participa da cascata como qualquer regra: a regra de entrada precisa ter a mesma
     especificidade da regra aberta (`dialog.x[open]:not([data-closing])`), senão a entrada não anima.
   - Sheet: a alça é o padding do próprio `<dialog>`, o cabeçalho leva `data-sheet-grip` e o corpo rolável
     `data-scroll`; a velocidade do flick é medida nos últimos 100 ms (> 0,5 px/ms fecha), não a média desde o
     início; um sheet arrastado até o fim fecha com `requestClose(true)`, sem repetir a transição.
   - `motion` foi instalado, medido e **removido**: `import { animate } from "motion"` custa 19 kB gzip (o plano
     estimava 5) para uma única mola. A mola de `use-sheet-drag.ts` é própria (vinte linhas: rigidez 320,
     amortecimento 26/36, parte da velocidade da mão, interrompível ao segurar de novo). Pesos medidos com
     rolldown, gzip: Base UI select 42 kB + tooltip 30 kB (parte compartilhada), Sonner 9 kB, NumberFlow 6 kB.
     O JS de produção foi de 142 para 215 kB gzip; a maior parte é o Base UI, que ficou por decisão do
     proprietário ("completo"). Se o peso incomodar, o próximo passo é carregar `select.tsx`/`tooltip.tsx`
     sob demanda (`React.lazy`) ou trocar o tooltip por uma implementação própria com o Popover API.
   - Tokens novos: `text-link` (brand-600), `text-link-hover` (700), `text-link-pressed` (800), `z-popover` (45,
     entre backdrop e modal, para popups portalados ao `<body>`), `scrim-hidden`. Os aliases legados saíram.
   - NumberFlow entrou na quantidade da lista, no contador de itens da navegação, nos totais da estimativa e
     no zoom do leitor (300 ms, `--ease-out`); os dígitos ficam em shadow DOM com `role="img"` e nome
     acessível, por isso o roteiro de fluxos lê a árvore de acessibilidade, não `innerText`.

Os planos executáveis de cada item estão em [plans/README.md](plans/README.md).
