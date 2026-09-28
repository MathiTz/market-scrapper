# Verificação das fases 1–4 do plano de UI e motion — 28/09/2026

Planos `003` a `009` de [plans/README.md](plans/README.md), executados nesta branch na ordem 009 → 007 → 003
→ 004 → 005 → 006 → 008, depois da fase 0 abaixo. Mesmo mock de API, snapshot congelado, relógio fixo e
larguras da auditoria. Nenhuma coleta, publicação, commit ou deploy. Desvios do texto dos planos:
[PLANO-UI-MOTION.md](PLANO-UI-MOTION.md), seção 12.

## Comandos

| Comando | Resultado |
|---|---|
| `npm run tokens` | 33 tokens de paleta + 57 semânticos (novos: `text-link` 600, `text-link-hover` 700, `text-link-pressed` 800, `scrim-hidden`, `z-popover`; os aliases legados `--green`, `--muted`… foram removidos) |
| `npm run tokens:check` | contraste: 32 pares ≥ mínimo; literais: 0 cores, 0 raios fora da escala e 0 `var(--x)` fora dos tokens (verificação nova) em `app/` e `components/` |
| `npm run typecheck` | aprovado |
| `npm test` | 106/106 |
| `npm run build` | aprovado (`prebuild` roda os dois checks); CSS 97,5 kB (17,5 kB gzip; fase 0: 77,6 / 14,7), JS 698 kB (215 kB gzip; fase 0: 476 / 142). Por biblioteca (rolldown, gzip): Base UI select 42 kB e tooltip 30 kB com parte comum, Sonner 9 kB, NumberFlow 6 kB; `motion` pesava 19 kB para uma mola e foi substituído por uma mola própria |

## Interface executada (medições no Chromium, 1280 e 390 px)

- Diálogo "Onde encontrar": entrada de 250 ms (opacidade 0 → 0,51 aos 100 ms → 1,00 aos 300 ms, fundo de
  0 % a 55 % junto); saída de 190 ms (aos 90 ms: opacidade 0,03, escala 0,96, `data-closing`); desmontado
  ao fim, foco de volta no botão "Onde encontrar". A entrada só animou depois de dar ao `@starting-style` a
  mesma especificidade da regra aberta.
- Select "Ordenar por": popup com `transform-origin` no gatilho e 6 itens; tooltip "Próximas" sobre a seta
  da faixa, também com origem no gatilho; segmentado do raio com a pílula em `translateX(82px)` sobre "5 km".
- Skeletons com a API em modo lento (8 s): 46 blocos na Hoje (faixa, cobertura, encartes) e grades na Buscar
  e nos Encartes; `.loading` continua no DOM, só para leitor de tela (e para os roteiros).
- Véu da busca: `.results[data-busy="true"]` enquanto `query !== search` (220 ms); a grade não é desmontada.
- Toasts: dois produtos adicionados em sequência empilham (2 `[data-sonner-toast]`); a 390 px ficam acima
  do dock, com a barra de busca ou sem ela.
- View Transitions: ao abrir um produto, `::view-transition-group(product-photo)` anima e o herói recebe
  `view-transition-name: product-photo`; ao voltar, o mesmo grupo anima, o foco vai ao `.product-open` e o
  cartão volta a ser marcado como herói. Pílula da navegação em `translateX(80px)`, 89 px, ao ir para
  "Buscar"; marcador do dock desliza para "Encartes". Faixa da Hoje com `data-first-load` e `rail-in` só na
  primeira carga; máscara apenas na borda que tem mais cartões.
- Bottom sheet a 390 px: sobe (translateY 485 px aos 60 ms → 0), página a 96 %, alça de 36 px; puxão de
  60 px solta e volta (continua aberto, sem transform inline); flick fecha, devolve o foco ao gatilho e
  remove `data-sheet-open`; "Onde encontrar" desce com `data-closing` (translateY 375 px aos 120 ms) e
  devolve o foco ao botão.
- Capturas: 110 cenas (320: 12, 390: 45, 768: 12, 1280: 41, incluindo a vitrine nas duas larguras), 0 px
  de rolagem horizontal, 0 erros de página; as 16 verificações sem imagem com o mesmo resultado da
  auditoria (lista com 3 itens após recarregar, Voltar do navegador, lista ilegível preservada, Desfazer no
  aviso, texto do timeout, offline/online). Uma rolagem de 5 px na vitrine a 390 px (gatilho do select que
  não encolhia) foi corrigida (`min-width: 0`) e a cena recapturada. Conjunto curado (19 imagens) em
  `referencias/auditoria-ux/fases1-4/`; relatório em `relatorios/capturas-fases1-4.json`.
- Fluxos (`referencias/auditoria-ux/scripts/flows.mjs`, Chromium a 390 e 1280 px e WebKit móvel no fluxo
  principal): **62/62**, os mesmos da auditoria: região → busca → filtro de rede (chip) → comparação com
  foco no título → quantidade 2 → Voltar do navegador → +1 na lista → recarregar com 3 mantidos; encarte →
  125 % → compartilhar → Esc devolve o foco; GPS negado → endereço manual; oferta antiga; cesta com itens
  faltantes; sem erros de página. Duas verificações precisaram ler a árvore de acessibilidade em vez do texto
  (quantidade e zoom, agora NumberFlow) e uma passou a contar `.filter-chips .chip`. Relatório em
  `relatorios/fluxos-fases1-4.json`.
- Hover (`referencias/auditoria-ux/scripts/hover-audit.mjs`, agora também sobre `.chip`, `.segmented-option`,
  `.select-trigger` e `.checkbox-field`): 78 tipos de elemento em 8 telas; 64 mudam em hover; os 14 restantes
  são o atalho "Ir para o conteúdo" (só visível no foco, 5 telas), a aba ou rede já selecionada (7) e o campo
  de busca (é o contêiner que muda, 2). Relatório em `relatorios/hover-fases1-4.json`.

## Limitações

Sem aparelho físico: o arrasto do sheet foi exercitado com ponteiro de mouse em emulação de 390 px, não com
o dedo, e o teclado virtual não foi testado. O Firefox não foi executado (a saída dos diálogos roda com
`data-closing` enquanto ainda estão abertos e não depende de `allow-discrete`; a entrada por
`@starting-style` existe desde o Firefox 129; sem View Transitions o produto abre sem o morph, como antes).
A vitrine força hover, foco e pressionado por atributos: mostra o desenho de cada estado, não o
comportamento. O Sonner impõe seu próprio `z-index` ao contêiner de toasts, fora da escala dos tokens.

---

# Verificação da fase 0 do plano de UI e motion — 27/09/2026

Planos `000` (tokens e canvas), `001` (tipografia) e `002` (motion tokens, reduced motion, pressionar) de
[plans/README.md](plans/README.md), executados nesta branch depois da auditoria abaixo.

## Comandos

| Comando | Resultado |
|---|---|
| `npm run tokens` | `app/tokens.css` com 33 tokens de paleta + 55 semânticos, gerado de `tokens/tokens.json` |
| `npm run tokens:check` | contraste: 32 pares ≥ mínimo (o menor: `border-default` sobre papel, 3,49:1 para 3:1; `price-regular` sobre papel, 4,83:1); literais: 0 hex/`rgb()`/`oklch()` e 0 raios fora da escala em `app/` e `components/` (antes: 84 hex) |
| `npm run typecheck` | aprovado |
| `npm test` | 106/106 |
| `npm run build` | aprovado (`prebuild` roda os dois checks); CSS 77,6 kB (14,7 kB gzip), JS 476 kB (142 kB gzip, inalterado), Archivo em 3 woff2 (latin 90 kB, latin-ext 86 kB, vietnamita 34 kB) |

Durante a migração, dois pares reprovaram e foram corrigidos **no JSON**, não no CSS: a borda de campo
(neutral-300, 1,53:1) subiu para um passo de L 63% (3,49:1); o anel de foco sobre o botão verde (1,64:1)
saiu da lista de pares porque fica 2 px fora do controle, sobre a superfície (11,6:1).

## Interface executada

Mesmo mock de API, snapshot congelado, relógio fixo e larguras da auditoria.

- Capturas de fase 0: 108 cenas nas mesmas larguras (320: 12, 390: 44, 768: 12, 1280: 40), 0 px de rolagem
  horizontal, 0 erros de página; as 16 verificações sem imagem do roteiro (lista com 3 itens após recarregar
  nas 4 larguras, Voltar do navegador, lista ilegível preservada, Desfazer, texto do timeout, offline/online)
  com o mesmo resultado da auditoria. Conjunto curado (17 imagens) em `referencias/auditoria-ux/fase0/`.
- No navegador: `body` em `"Archivo Variable"`, fonte carregada (`document.fonts`), `.price` com
  `font-variation-settings: "wdth" 90` e `font-variant-numeric: tabular-nums`, `h1` 28 px no desktop e
  24 px no mobile, canvas `rgb(249, 251, 253)`.
- `hover-audit` (`referencias/auditoria-ux/scripts/hover-audit.mjs`): 82 tipos de elemento em 8 telas;
  66 mudam em hover; os 16 restantes são estados selecionados (aba, chip, rádio de raio), o atalho "Ir para o
  conteúdo" (só visível no foco) e o campo de busca (o contêiner é quem muda). Relatório em
  `relatorios/hover-fase0.json`.
- Dois problemas encontrados nas capturas e corrigidos antes do conjunto final: cabeçalho com faixa branca
  mais estreita que a página no desktop (o cabeçalho voltou a assentar no canvas) e `h1`/preço um passo
  grandes demais no mobile (a camada de fase 0 ganhou a media query de 760 px).
- Incidente de ambiente: o Vite serviu uma versão antiga de `globals.css` depois de duas gravações no mesmo
  segundo; um `touch` no arquivo forçou o HMR. Registrado para as próximas fases.

Limitações: sem aparelho físico; `tnum` confirmado só pelo navegador (a propriedade está ativa; a fonte
tem numerais tabulares); o preload do woff2 não foi feito (nome com hash no build), e o fallback com
métricas do capsize evita o salto de layout no `swap`; os aliases legados (`--green`, `--muted`…) ainda
existem em `tokens.css` até os planos 007 e 009.

---

# Verificação da auditoria de UX — 27/09/2026

Base `main` @ `12e46d0`; alterações na branch local `ux/auditoria-experiencia`. Windows 11, Node 24.16.0,
npm 11.13.0. `npm ci` com cache isolado (o cache global deste computador falhou com `EEXIST`, como já
registrado em 21/09). Nenhuma coleta, publicação, push ou deploy.

## Comandos

| Comando | Antes (`12e46d0`) | Depois |
|---|---|---|
| `npm run typecheck` | aprovado | aprovado |
| `npm test` | 1ª execução: 70/72, 2 falhas por **timeout de 5 s** no primeiro uso de `Intl` (`flyers.test.ts`, `stock.test.ts`); 2ª e 3ª execuções: 72/72 | 106/106 em 12 arquivos (34 testes novos) |
| `npm run build` | aprovado; JS 450,39 kB (134,95 kB gzip), CSS 47,08 kB | aprovado; JS 476,07 kB (142,27 kB gzip), CSS 52,93 kB (10,99 kB gzip) |

As falhas da primeira execução da base são de ambiente (carregamento frio do ICU no Windows), não de lógica:
os mesmos testes passam nas execuções seguintes e com `--testTimeout=60000`. O build da base gera os mesmos
hashes de arquivo que o site publicado, então as observações de produção valem para este commit.

Testes novos: `format.test.ts` (embalagem, preço por kg/L, horário em Fortaleza, nome na lista),
`comparison.test.ts` (diferença implausível, rótulo de menor preço, motivos fora da comparação),
`list-storage.test.ts` (lista ilegível preservada em cópia, parcial, armazenamento bloqueado),
`deals.test.ts` (economia entre redes e guarda de 3×), `domain.test.ts` (textos de condição); ampliados:
`search.test.ts` (relevância), `filters.test.ts` (ordem por relevância), `flyers.test.ts` (encarte sem data final).

## Interface executada

Vite dev servindo uma cópia congelada do snapshot público de 27/09/2026 por um servidor local de teste
(também simula 503, 500, demora, ausência de resposta e snapshot vazio). Relógio fixo em 27/09/2026 18:00,
Chromium headless (Playwright 1.63), larguras 320, 390, 768 e 1280 px.

- Capturas: 112 (antes) e 115 (depois) cenas; **rolagem horizontal 0 px em todas**; nenhum erro de página.
  Uma execução intermediária registrou uma falha de WebSocket do recarregamento do Vite (infraestrutura de
  desenvolvimento), que não se repetiu na execução final.
- Roteiro de fluxos com asserções (Chromium a 390 e 1280 px; WebKit emulando celular no fluxo principal):
  **antes 39/59, depois 62/62**. As falhas do antes são os pontos corrigidos: nenhum chip de filtro ativo;
  foco perdido no `body` ao abrir o produto; Voltar do navegador saindo do app (`about:blank`); preço antigo
  sem motivo; nenhum aviso de cesta incompleta; subtotais sem rótulo de parcial; sem atalho para o conteúdo.

| Fluxo pedido | Resultado (depois) |
|---|---|
| Escolher região → buscar → filtrar → comparar → adicionar → editar → recarregar | aprovado: região única (Fortaleza) exibida como cobertura; referência manual "Aldeota" + raio; busca; filtro de rede com chip; comparação com foco no título; quantidade 2 no detalhe; Voltar do navegador fecha o produto; +1 na lista; após recarregar, quantidade 3 mantida |
| Abrir encarte → ampliar → compartilhar → reabrir | aprovado até compartilhar: leitor abre, 125%, retorno "Copie o link abaixo…" (sem Web Share nem área de transferência no navegador de teste), Esc fecha e devolve o foco. **Reabrir no app não existe**: o link é a imagem na origem da rede (backlog P3-03) |
| Negar GPS → informar região manualmente | aprovado: "Localização não autorizada. Você pode digitar seu endereço…", endereço "Meireles" aplicado |
| Perder conexão → recuperar | aprovado: offline oculta os cartões e explica; ao voltar, 12 cartões reaparecem sem recarregar |
| Abrir oferta vencida | aprovado (demo, preço de 48 h): aviso "O preço deste link não está mais atual…", preço listado fora da comparação com motivo, nenhuma linha na comparação. O snapshot real não tinha nenhuma oferta vencida ou desatualizada |
| Comparar uma cesta com itens faltantes | aprovado: aviso "Nenhuma rede tem preço atual para todos os 3 itens…", todos os valores "Subtotal parcial", nenhuma rede marcada como mais barata |

Medições pontuais (antes → depois):
- Timeout da API: "signal timed out" → "A consulta das ofertas demorou mais que o esperado."
- Lista salva ilegível: valor substituído por `[]` sem aviso → cópia em `med-list-real-copia-<hash>` e aviso.
- Remoção da lista: sem desfazer → "Desfazer" restaura os itens.
- Busca "leite integral": 1º resultado "Leite de Coco…" → "Leite Xandô Integral A2 1l".
- Destaque do dia: "Laranja-pera 18kg, R$ 45,10 a menos" → "Whisky Old Parr 12 Anos 1l, R$ 40,00 a menos que no Pinheiro Supermercado" (diferença de 1,36×).

Contraste (fórmula WCAG 2.x): foco #87bd54 sobre #f6f8f7 2,09:1 → #173d30 11,27:1; texto secundário
#66776d 4,45:1 (fundo) e 4,14:1 (painéis) → #5b6c62 5,23:1 e 4,86:1; menu inferior #6b7e72 4,33:1 → 5,58:1.

## Limitações

Não houve aparelho físico, GPS real (o navegador de teste nega a permissão), teclado virtual, leitor de tela
real (nomes acessíveis conferidos por árvore de acessibilidade e código), zoom de texto do navegador
(o reflow foi conferido a 320 px, equivalente a 400% de 1280 px), instalação PWA, compartilhamento nativo
entre aplicativos nem login administrativo. O aviso de "falha ao atualizar com dados já carregados" foi
verificado pelo código, não por captura. Os dados são um único snapshot, sem ofertas vencidas nem encartes
sem data final; esses estados foram exercitados com a demonstração e com testes unitários. A conformidade
com WCAG 2.2 AA não é declarada: foram corrigidos os problemas encontrados nos critérios verificados.

---

# Verificação da entrega de handoff — 21/09/2026 (histórico)
- Instalação limpa com npm ci: aprovada (cache local alternativo; o cache global deste computador falhou).
- npm run typecheck: aprovado.
- npm run build: aprovado; Next.js 16.3.5, build webpack.
- Build servido localmente e navegado em Chromium headless, larguras 320, 390 e 1280px.
- Em cada largura: Hoje, abrir leitor de encarte, buscar café, abrir comparação, adicionar à lista e recuperar lista após recarregar: aprovados.
- Nenhum erro JavaScript não tratado nos fluxos verificados.
- Sem transbordamento horizontal da página inicial nas três larguras.
- Raiz, login, manifesto e duas páginas SVG de encarte responderam HTTP 200.
- Endereço respondeu 501 e sessão retornou actor null, conforme limites de demonstração.
- Doze capturas novas e resultados estruturados em referencias/preview.
- Inspeção visual direta das capturas Hoje em 390px e comparação em 1280px.
- Componentes originais e CSS comparados por SHA-256 com a origem.
- ZIP inspecionado após criação; arquivos inventariados e hashes conferidos.

Limites: não se executou a suíte completa do projeto original, nem testes em aparelho físico, backend de destino, login real, GPS real, compartilhamento entre aplicativos ou instalação PWA. As capturas em referencias/historicas e os relatórios citados nos textos originais são evidências anteriores, não testes desta entrega.
O aviso original "Voltar aos dados reais" aponta para a raiz, que também é demonstrativa neste pacote. Não há dados reais no pacote.