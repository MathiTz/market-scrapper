# Referência visual
## Fonte de verdade
Componentes e app/globals.css são a implementação atual. Capturas são apoio. referencias/historicas contém estados de momentos diferentes do projeto; para divergências, priorize o código atual e referencias/preview. A auditoria de 27/09/2026 (docs/auditoria-ux-capturas.md) não teve suas imagens mantidas no repositório.
## Estilo
Archivo Variable (peso 100–900, largura 62–125), auto-hospedada via `@fontsource-variable/archivo`, com fallback de métricas ajustadas para Arial. Ícones lucide-react.
Tokens: a fonte única é `tokens/tokens.json` (paleta em OKLCH → semântica → `app/tokens.css`, gerado por `npm run tokens`). O CSS consome só nomes semânticos com prefixo `--md-` (`surface-canvas` #f9fbfd, `surface-level-1` #fff, `text-primary`, `text-secondary`, `text-link*`, `border-subtle`, `interactive-primary-fill-*`, `selected-*`, `messaging-*`, `price-*`, `elevation-*`, `radius-*`, `space-*`, `z-*`) mais os tokens de motion (`--ease-out`, `--dur-*`). Não há mais aliases legados. `npm run tokens:check` reprova contraste abaixo de 4,5:1 (texto) ou 3:1 (foco, borda de campo), qualquer literal de cor ou raio fora da escala e qualquer `var(--x)` que não seja token nem variável local declarada, em `app/` e `components/`; roda no `prebuild`.
Escala de tipo fixa em rem (12 · 13 · 14 · 16 · 18 · 20 · 24 · 28 · 34). O preço é a única licença: largura 90, peso 700, numerais tabulares, tinta `price-ink`. Nada de decisão abaixo de 12px. Reduced motion reduz (mantém fades, zera deslocamentos); hover só com ponteiro fino; todo pressionável encolhe a 97% ao toque.

Componentes (`components/ui/`): `Button`/`IconButton` (quatro variantes, três tamanhos, `loading`), `TextField`, `Chip`/`ChipCheckbox`, `SelectField` e `Tooltip` (Base UI, encapsulados só nesses dois arquivos), `CheckboxField` (nativo desenhado), `Segmented`, `Skeleton*`, `Count`/`Money` (NumberFlow), e os hooks `useDialog` (entrada 250 ms, saída 190 ms, foco devolvido), `useSheetDrag` (arrasto com mola própria, sem biblioteca) e `useIndicator` (pílula que desliza). Toasts em `lib/notify.tsx` (Sonner); View Transitions em `lib/view-transition.ts`. A vitrine de todos os estados está em `/demo?vitrine=1` (`components/vitrine.tsx`) e nunca na rota real. Abaixo de 760 px, "Perto de você", "Onde encontrar" e "Tamanhos" são bottom sheets. Cada camada de estilo está comentada no fim de `app/globals.css` ("Phase 1 (plan 009)" …); o raciocínio e os desvios estão em [PLANO-UI-MOTION.md](PLANO-UI-MOTION.md), seção 12.
Quebras de layout: 1200, 1024, 760 e 460px, além de regras para pouca altura.
Plano e estado da evolução visual: [PLANO-UI-MOTION.md](PLANO-UI-MOTION.md) e [plans/README.md](plans/README.md).
## Mapa
| Experiência | Arquivos em components/ |
|---|---|
| Navegação, Hoje, Buscar, detalhe e lista (estado e composição) | market.tsx |
| Linha de preço da comparação | offer-row.tsx |
| Cartões e fotos/fallback | product-card.tsx; product-range-card.tsx |
| Estados de erro, sem conexão e vazio | status-panel.tsx |
| Como ler os preços e redes acompanhadas | sources.tsx |
| Faixa horizontal de ofertas | offer-rail.tsx |
| Endereço/GPS | nearby-filter.tsx |
| Onde encontrar (alcance do preço, unidade) e contato | store-location.tsx; store-contact.tsx |
| Estimativa por rede | store-estimates.tsx |
| Compartilhar | offer-share.tsx |
| Redes, períodos e arquivo de encartes | flyers.tsx |
| Leitor, zoom e navegação | flyer-stories.tsx; flyer-player.tsx |
| Primitivos (botão, campo, chip, select, tooltip, checkbox, segmentado, skeleton, número) e hooks de diálogo, sheet e indicador | ui/*.tsx, ui/*.ts |
| Vitrine de componentes e estados (`/demo?vitrine=1`) | vitrine.tsx |
| Administração | admin.tsx |

Regras de apresentação em lib/: format.ts (embalagem, preço por kg/L, "visto hoje às…"), comparison.ts (rótulo de menor preço, diferença implausível, preços fora da comparação), snapshot.ts (carga e mensagens de erro), list-storage.ts (lista salva e seus problemas).
## Aceite após integração
- Conferir 320, 390, 768 e 1280px; sem rolagem horizontal da página (a faixa de ofertas tem rolagem própria).
- Preservar hierarquia: preço, condição logo abaixo, embalagem, rede, "visto …", local.
- Nenhum "menor preço" com um preço só; empate marcado; filtros ativos no rótulo.
- Nenhuma economia nem preço por kg/L quando os preços da mesma comparação diferem 3× ou mais.
- Sem referência de local, nenhuma filial é apresentada como "a loja" da oferta.
- Conferir Hoje, Buscar, comparação, Minha lista e Encartes.
- Conferir erro de API, demora, sem conexão (com e sem dados), snapshot vazio: nenhum deles com texto de "sem ofertas".
- Conferir oferta antiga (demo), clube, ausência de foto, busca vazia por termo e por filtros.
- Conferir quantidade, desfazer e persistência da lista após recarregar; lista ilegível guardada em cópia.
- Conferir modais, foco de teclado, Voltar do navegador, leitor de encartes, pausa, zoom e arquivo.
- Conferir compartilhar e reabrir produto/oferta por link.
As capturas de auditoria usam uma cópia congelada do snapshot público de 27/09/2026; as de referencias/preview usam dados fictícios e o aviso de demonstração.
