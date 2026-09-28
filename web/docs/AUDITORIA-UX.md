# Auditoria de UX/UI e evolução da interface — Mercado em Dia

27/09/2026. Jornada completa e matriz de estados: [ESTADOS-UX.md](ESTADOS-UX.md). Método das capturas
comparativas usadas nesta auditoria: [auditoria-ux-capturas.md](auditoria-ux-capturas.md) (as imagens em si
não foram mantidas no repositório).

## 1. Resumo do diagnóstico e direção adotada

A interface já tinha uma base sólida: preços em centavos, comparação separada de alternativas, condições de
clube tratadas no ETL, preços antigos fora do ranking, lista sem cadastro, localização opcional com
explicação de privacidade, leitor de encartes com pausa e teclado, nenhuma rolagem horizontal de 320 a
1280 px. Os problemas estavam na **camada de apresentação**, em lugares onde ela afirmava mais do que os dados sustentam:

1. **A "oferta do dia" em destaque era falsa** com os dados reais: "Laranja-pera 18 kg" por R$ 0,80
   (R$ 0,04/kg), "R$ 45,10 a menos" que uma caixa de 18 kg de R$ 45,90. É uma correspondência entre um item
   sem tamanho e uma caixa. Em 4 dos 92 produtos vendidos por duas ou mais redes a diferença passa de 3×,
   e todos são produtos vendidos por peso ou em caixa.
2. **Falha de serviço e falta de conexão apareciam como "não há ofertas"** ("Ainda não temos preços
   validados", "Nenhum produto encontrado"), ao lado de uma cobertura que dizia "4773 ofertas atuais".
3. **Afirmações sem escopo**: "Menor preço encontrado" num produto com um único preço (≈98% do catálogo),
   subtotal de 1 de 3 itens com o mesmo destaque de um total, endereço de uma filial escolhida pelo centro da
   cidade apresentado como "Localização da loja" de um preço que é do site da rede.
4. **Continuidade**: o botão Voltar do navegador saía da busca; remover da lista não tinha desfazer; uma
   lista salva ilegível era sobrescrita sem aviso; busca por "leite integral" trazia leite de coco primeiro.
5. **Acessibilidade**: anel de foco com 2,1:1; texto secundário a 4,45:1 no fundo; preço dos cartões
   ausente do nome acessível; informação de decisão em 9–10 px.

**Direção:** completar a experiência existente sem trocar marca, stack, navegação ou regras de domínio.
Cada afirmação passou a dizer o próprio alcance: "Único preço", "Empate", "com os filtros atuais", "Preço
do site", "Só para membros do PinClube", "Subtotal parcial". Cada falha ganhou um estado próprio, com o que
aconteceu, o que continua possível e como seguir. Onde a correção depende de dados, a interface ficou
conservadora (sem economia, sem preço por kg, com aviso), e o contrato necessário foi registrado no backlog.

## 2. Escopo, fontes e método

- **Repositório:** `github.com/MathiTz/market-scrapper`, branch `main` @ `12e46d0` (clonado em 27/09/2026).
  Alterações na branch local `ux/auditoria-experiencia`, **sem push, deploy, coleta ou publicação**.
  A pasta `G:\mercado-em-dia-mvp\mercado-em-dia` é outro projeto (MVP anterior em Next.js, sem git) e não foi
  tocada.
- **Produção corresponde a este commit:** o build local gera os mesmos hashes que o site publicado
  (`index-D_0MGM7A.js`, `index-C2OuxGlG.css`).
- **Dados:** cópia congelada do snapshot público (`GET /api/public` do site de produção em 27/09/2026 17:57;
  `generated_at` 12:04, Fortaleza): 4.086 produtos, 4.773 ofertas (todas `catalog`, todas vigentes), 8 redes,
  115 unidades, 8 encartes (todos da Cometa), 587 preços de clube, **1 região (Fortaleza)**, 0 telefones.
  Servida localmente por um servidor de teste, fora do repositório, que também simula 503, 500, demora,
  ausência de resposta e snapshot vazio; a busca de endereço foi encaminhada ao serviço público (Photon).
  A API Flask local não foi usada porque monta os encartes buscando os sites das redes, o que equivale a uma coleta.
- **Execução:** Vite dev (Node 24.16), Chromium e WebKit do Playwright 1.63, relógio fixo em 27/09/2026 18:00,
  larguras 320, 390, 768 e 1280 px. Mesmas telas, dados e tamanhos no antes e no depois; o "antes" de cenários
  acrescentados depois veio de uma worktree temporária do commit original.
- **Evidência:** [O] observada na interface executada, [C] lida no código, [H] hipótese a validar.
- **Documentação desatualizada:** `README.md`, `ALTERACOES.md`, `INTEGRACAO.md` e `VALIDACAO.md` desta pasta
  descrevem o pacote de handoff em Next.js de 21/09; `AGENTS.md` e o código são a referência atual.

## 3. Inventário de telas, componentes e pontos de contato

Classificação do estado **antes** das alterações.

| Recurso | Onde | Classificação | Observação | Depois |
|---|---|---|---|---|
| Hoje | `market.tsx` | existente com problemas | ordem alfabética sob "Menores preços"; destaque falso; zeros ao carregar; erro/offline como vazio | ordem por desconto informado, destaque só plausível, estados próprios |
| Buscar | `market.tsx` | existente com problemas | ordem por desconto com termo; sem contagem; filtros ativos invisíveis; vazio genérico | relevância com termo, contagem, ordem e chips visíveis, vazios distintos |
| Detalhe e comparação | `market.tsx` | existente com problemas | preço fora da 1ª dobra no mobile; "menor" em preço único; preços fora da comparação somem | resumo no topo, rótulos com escopo, preços fora da comparação explicados |
| Minha lista | `market.tsx`, `list-adder.tsx`, `store-estimates.tsx` | existente com problemas | sem desfazer; armazenamento; subtotal parcial destacado | desfazer, avisos persistentes, cópia de segurança, parcial rotulado |
| Encartes (lista, arquivo, leitor) | `flyers.tsx`, `flyer-stories.tsx`, `flyer-player.tsx` | existente e adequado | pausa, teclado, zoom, movimento reduzido; rótulo "Em vigor" sem data final ([C]) | rótulo sem promessa de validade |
| Demonstração `/demo` | `lib/demo.ts` | existente e adequado | isolada, aviso fixo, telefone e endereço fictícios marcados; produto com preço antigo inalcançável na busca | produto alcançável |
| Administração `/admin` | `admin.tsx` | não verificável | a API responde `actor: null` e 501 ao login; fluxos de confiabilidade vivem no pipeline Python | link removido do rodapé público; código intocado |
| Offline (PWA) | `public/sw.js`, `offline.html` | parcialmente implementado | só a página offline e o ícone ficam em cache; preços ocultos offline | mensagens corretas; política mantida |
| Cartão de produto | `product-card.tsx` | existente com problemas | preço fora do nome acessível; rede e base da economia em `title`; filial arbitrária; sem horário | hierarquia revista (seção 6.2) |
| Cartão de tamanhos | `product-range-card.tsx` | existente com problemas | faixa de preço sem tamanhos; linhas fora de ordem | "a partir de" com tamanho, melhor preço por kg/L |
| Localização (Perto de você) | `nearby-filter.tsx` | existente e adequado | GPS só por clique, mensagens por causa, privacidade explicada, `sessionStorage` | inalterado |
| Onde encontrar | `store-location.tsx` | existente com problemas | "Localização da loja" de um preço do site; mapa de filial arbitrária | alcance do preço primeiro; filial só com referência |
| Contato | `store-contact.tsx` | não verificável | 0 telefones nos dados; "Telefone não informado" repetido em cada item | telefone só quando existir |
| Compartilhar oferta | `offer-share.tsx` | existente e adequado | nativo → cópia → campo; cancelar é silencioso; condição no texto | texto alinhado à tela |
| Link compartilhado | `market.tsx` | existente com problemas | aviso de "oferta indisponível" também em link sem oferta ([C]) | corrigido; mensagens explicativas |
| Região | cabeçalho | não aplicável | 1 região; `<select>` com uma opção | rótulo fixo |
| Cobertura e fontes | `market.tsx` | parcialmente implementado | "preços validados"; contagens brutas; sem data; link vazio (Carnaúba) | "Como ler os preços", contagens atuais, datas por rede |
| Metodologia / ajuda | — | ausente | nada explicava idade máxima, alcance do preço, equivalência | seção "Como ler os preços" |
| Reportar preço divergente | — | ausente | não há canal de suporte | backlog (não implementado: não há destino real) |
| Favoritos, alertas, notificações | — | ausente (por decisão) | sem conta, sem push | backlog |
| Voltar do navegador | — | ausente | saía do app | histórico por produto |
| Desfazer remoção | — | ausente | — | implementado |
| Teclado virtual sobre o dock | mobile | não verificável | exige aparelho real [H] | — |

## 4. Jornada e estados

Resumo; o detalhe está em [ESTADOS-UX.md](ESTADOS-UX.md) (23 etapas, 9 grupos de estados, antes e depois).
Lacunas por tipo de solução:

| Lacuna | Tipo de solução |
|---|---|
| Erro, timeout, offline e snapshot vazio distinguidos | estado faltante (componente `StatusPanel`) |
| Voltar preserva termo, rolagem e foco | ligação entre fluxos (histórico) |
| Filtros ativos e ordem visíveis | melhor visibilidade (chips, contagem) |
| Preços fora da comparação | seção nova no detalhe (`<details>`) |
| Como ler os preços | seção nova em Hoje (sem tela nova) |
| Desfazer, armazenamento | mensagem persistente na lista |
| Reportar preço, alertas, reabrir encarte no app | nova funcionalidade → backlog |

## 5. Achados priorizados

P0 = pode induzir decisão materialmente errada; P1 = fricção importante na jornada principal; P2 =
consistência, legibilidade e refinamento; P3 = oportunidade futura. Linhas de código referem-se a `12e46d0`.
Esforço: B (horas), M (1–2 dias), A (mais que isso ou dependente de outra equipe).

| ID | Jornada / tela | Evidência | Problema | Impacto | P | Esforço | Tipo | Solução | Dependência | Critério de aceite | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P0-01 | Hoje, cartão, detalhe | [O] `antes/390-hoje-topo`, `antes/1280-comparacao-suspeita`; `lib/deals.ts:16-21`; `product-card.tsx:93,156-176`; dados: 4/92 comparações ≥3× | destaque "R$ 45,10 a menos" e R$ 0,04/kg entre caixa de 18 kg e item unitário | pessoa escolhe loja ou preço que não existe | P0 | B (UI) / M (ETL) | ajuste de interação | guarda de plausibilidade (≥3×): fora do destaque, sem economia, sem preço por kg, sem "menor preço", aviso no cartão e no detalhe | correção definitiva no matching (D-01) | nenhuma economia ou "menor preço" com razão ≥3×; aviso visível | implementado (mitigação) |
| P0-02 | Hoje, Buscar, Encartes, detalhe, lista | [O] `antes/390-estado-erro-503`, `-busca`, `-offline`; `market.tsx:344-351,974-1000,1236-1263,1319-1324` | erro de API e falta de conexão mostrados como "não há preços/produtos" | pessoa conclui que não há oferta; não sabe que pode tentar de novo | P0 | M | estado faltante | `StatusPanel` de erro e offline por tela; itens "Preço oculto sem conexão"; refetch sem recarregar | — | nenhuma tela usa estado vazio quando a causa é serviço ou conexão | implementado |
| P1-01 | Cartão, Onde encontrar, lista | [O] `antes/390-ver-localizacao`; `product-card.tsx:85-90,137-139`; `store-location.tsx:25-31,56` | endereço da filial mais próxima do **centro** exibido como "a loja" de um preço do site | ida a uma filial arbitrária esperando o preço | P1 | M | correção de conteúdo | sem referência: "n unidades · defina seu local"; diálogo começa pelo alcance do preço ("não confirmado em uma unidade física"); filial só com referência, com distância em linha reta | escopo por filial (D-03) | nenhum endereço de filial sem referência da pessoa | implementado |
| P1-02 | Hoje | [O] `antes/1280-hoje-topo`; `market.tsx:350-356,928` | "Ofertas do dia · Menores preços" em ordem alfabética ("100% Pure Whey"…) | ofertas úteis escondidas; título inexato | P1 | B | ajuste de interação | ordem por maior desconto informado pela loja (mesma regra da busca), subtítulo que diz o critério | [H] validar se "maior desconto" é o melhor critério | ordem e subtítulo coincidem | implementado |
| P1-03 | Detalhe | [O] `antes/390-clube-incluido`; `market.tsx:696-700` | "Menor preço encontrado" com um único preço, em empate só na 1ª linha e em preço de clube sem ressalva | afirmação comparativa sem comparação | P1 | B | correção de conteúdo | `lowestPriceLabel`: "Único preço", "Empate", "com os filtros atuais", "(com condição)" | — | rótulo só com ≥2 preços; empates marcados | implementado |
| P1-04 | Buscar | [O] `antes/390-busca-leite` ("Leite de Coco" primeiro); `market.tsx:1058-1263` | ordem padrão ignora o termo; sem contagem; ordem e filtros ativos só no painel; vazio genérico | busca parece errada; filtros esquecidos | P1 | M | ajuste de interação | "Mais relevantes" com termo; contagem em `role=status`; ordem visível; chips removíveis; vazio por termo, por filtros e por raio | — | com termo, nome que começa pelo termo vem antes; filtros ativos visíveis com o painel fechado | implementado |
| P1-05 | Minha lista | [O] `antes/1280-lista-completa`; `store-estimates.tsx:26-41` | subtotal de 1 de 3 itens com o mesmo destaque de um total; nenhum aviso quando nenhuma rede cobre a lista | loja parcial parece mais barata | P1 | B | correção visual | "Total estimado" × "Subtotal parcial" (atenuado), "faltam n itens", aviso quando nenhuma rede completa, itens "não somado" | — | parcial nunca com o destaque de total | implementado |
| P1-06 | Minha lista | [O] `lista-armazenamento-ilegivel` (valor final `[]`), `antes/390-lista-apos-remover`; `market.tsx:142-158,192-199,1307-1314,1394-1404` | remover sem desfazer (inclusive em lote); falha de gravação só em aviso de 2,8 s; lista ilegível sobrescrita | perda silenciosa da lista | P1 | M | estado faltante | desfazer persistente; `readList`/`writeList` com cópia do valor ilegível e avisos persistentes | — | nada apagado sem cópia ou sem desfazer | implementado |
| P1-07 | Buscar → detalhe | [O] `voltar-do-navegador` (antes: saía da página); `market.tsx:276-279,610-617` | Voltar do navegador sai da busca; rolagem e foco perdidos | retrabalho, sobretudo no celular | P1 | M | ligação entre fluxos | `pushState` com `?produto=`; `popstate` fecha; rolagem e foco no cartão de origem | — | voltar preserva termo, filtros, rolagem e foco | implementado |
| P1-08 | Cartões | [C] `product-card.tsx:105-108` (`aria-label` só com nome; filhos de botão são apresentacionais) | leitor de tela não ouve o preço nos cartões | exclusão de pessoas com deficiência visual | P1 | B | acessibilidade | nome acessível com nome, embalagem, preço, rede e condição | — | preço presente no nome acessível | implementado |
| P1-09 | Cartões | [C] `product-card.tsx:163-175` | rede da 2ª oferta e base da economia só em `title` | informação de decisão escondida em tooltip | P1 | B | correção de conteúdo | "também R$ x no Y"; "R$ x a menos que no Y" | — | nenhuma informação comercial só em tooltip | implementado |
| P1-10 | Cartões | [O] `antes/390-hoje-topo`; `product-card.tsx:134-155,198-202` | sem horário de observação; condição abaixo do endereço; aviso de preço online em 10 px com opacidade | "ainda é válido?" sem resposta | P1 | B | correção visual | condição logo abaixo do preço; "Preço do site · visto hoje às 12:03" | — | condição e horário visíveis no cartão | implementado |
| P1-11 | Hoje | [O] `antes/390-estado-carregando`; `market.tsx:224-230,1010-1032` | cobertura "preços validados", contagens brutas (inclui variantes de clube) como "ofertas atuais", zeros ao carregar, publicação nunca exibida, falha de atualização sem aviso | confiança mal calibrada | P1 | B | estado faltante | "Ofertas monitoradas", contagem de preços atuais, "Dados publicados hoje às 12:04", aviso de atualização falha com horário | último sucesso por rede (D-07) | nenhum zero antes dos dados; horário visível | implementado |
| P1-12 | Todas | [O] `antes/390-estado-timeout` ("signal timed out"); `market.tsx:212-219` | mensagem técnica do navegador ao consumidor | ruído e desconfiança | P1 | B | correção de conteúdo | `loadSnapshot` com mensagens por causa (tempo, rede, formato, serviço) | — | nenhuma mensagem técnica | implementado |
| P1-13 | Global | [C] `globals.css:8,62,1830,2503`; contraste calculado | foco #87bd54 (2,1:1, WCAG 1.4.11); `--muted` 4,45:1 no fundo e 4,14:1 nos painéis (1.4.3); menu inferior 4,33:1 a 11 px | foco e textos secundários difíceis de ver | P1 | B | acessibilidade | `--focus` #173d30 (11:1), `--muted` #5b6c62 (≥4,86:1), rótulos do menu com o token | — | todos os pares ≥4,5:1 (texto) e ≥3:1 (foco) | implementado |
| P1-14 | Detalhe (mobile) | [O] `antes/390-comparacao` | preço só depois da primeira tela | resposta principal escondida | P1 | B | correção visual | resumo "Menor/Único preço atual … · n preços · Ver comparação" sob o título | — | preço visível sem rolar a 390 px | implementado |
| P1-15 | Detalhe, Buscar | [O] `antes/390-demo-busca-preco-antigo`; `market.tsx:418` | preços vencidos/desatualizados sumiam sem explicação; produto só com preço antigo não era encontrável | "o produto sumiu?" | P1 | B | estado faltante | "n preços fora da comparação" com motivo; opção "sem preço atual" quando há preços antigos | — | vencido ≠ desatualizado no texto | implementado |
| P2-01 | Condições | [O] `antes/390-clube-incluido`; `domain.ts:90`; dados: `club: "Clube"` (Centerbox) | "Clube PinClube", "Clube Clube" | leitura truncada da condição | P2 | B | correção de conteúdo | "Só para membros do PinClube / do clube da loja" | — | condição diz quem paga | implementado |
| P2-02 | Cartão, detalhe, lista | [O] "18000 g", "1 embalagem · 600 g"; `product-card.tsx:115-118`; `market.tsx:301,625-626` | tamanhos em gramas, "1 un" para tamanho desconhecido (166 produtos), nome da lista duplicado | leitura lenta; preço "/un." enganoso | P2 | B | correção de conteúdo | `packLabel`, `unitPriceText`, `listName` | — | "18 kg", "12 × 350 ml", "Tamanho não informado" | implementado |
| P2-03 | Cartão de tamanhos | [O] `antes/390-tamanhos-dialogo`; `product-range-card.tsx:118-126,158` | faixa sem tamanhos; linhas fora de ordem | "a partir de" sem referência | P2 | B | correção visual | "a partir de R$ x na embalagem de y"; menor preço por kg/L; ordem por tamanho | — | "a partir de" sempre com tamanho | implementado |
| P2-04 | Global | [C] `globals.css:1252,2998-3028` | distância, aviso, rótulo de menor preço e "Sem foto" em 9–10 px | legibilidade | P2 | B | correção visual | mínimo de 11–12 px para informação de decisão, editado no lugar | — | nenhum texto de decisão < 11 px | implementado |
| P2-05 | Cabeçalho 768 px | [O] `antes/768-hoje-topo` | "Minha lista" em duas linhas | desalinhamento | P2 | B | correção visual | `nowrap` + espaçamento ≤1024 px | — | menu numa linha a 768 px | implementado |
| P2-06 | Cabeçalho | [O]; `market.tsx:564-583` | `<select>` de região com uma opção | controle sem efeito | P2 | B | correção visual | rótulo fixo quando há uma região | nova região no snapshot reativa o seletor | — | implementado |
| P2-07 | Rodapé | [O]; `market.tsx:1474`; API 501 | link "Administração" público para login inoperante | navegação administrativa misturada | P2 | B | correção de conteúdo | link removido (rota mantida) | D-08 | — | implementado |
| P2-08 | Fontes | [O]; `market.tsx:1455-1462`; dados: Carnaúba `official_url: ""` | link vazio | clique sem destino | P2 | B | correção | sem link quando não há URL | — | — | implementado |
| P2-09 | Encartes | [C] `flyers.ts:46,62` | "Dentro da validade"/"Em vigor" sem data final da fonte | promessa de validade | P2 | B | correção de conteúdo | "Publicado, sem data final" / "Data final não informada" | data final na fonte | — | implementado (estado latente: nenhum encarte assim no snapshot atual) |
| P2-10 | Lista | [O] aviso "Adicionado à sua lista" | aviso sem nome; item repetido sem retorno | incerteza | P2 | B | ajuste de interação | "“Nome” adicionado", "Agora são n de “Nome”", "✓ n" no cartão | — | — | implementado |
| P2-11 | Global | [O] `notice amber` renderizado em cinza (ordem do CSS) | aviso de alerta sem cor de alerta | hierarquia de avisos | P2 | B | correção visual | `.notice.amber` explícito | — | — | implementado |
| P2-12 | Lista, diálogo | [O]; `store-contact.tsx:27-29` | "Telefone não informado" em cada item | ruído | P2 | B | correção de conteúdo | telefone só quando existir; ausência dita uma vez no diálogo | D-06 | — | implementado |
| P2-13 | Detalhe (mobile) | [O] `antes/390-comparacao-com-referencia` | ações de cada linha em posições diferentes; rede repetida no subtítulo | leitura irregular | P2 | B | correção visual | grupo de preço + grupo de ações em grade | — | ações na mesma posição em todas as linhas | implementado |
| P2-14 | Seleção | [C] categorias só por cor; abas sem `aria-current` | estado de seleção não anunciado | acessibilidade | P2 | B | acessibilidade | `aria-pressed`, `aria-current`, ✓ nos chips de rede | — | — | implementado |
| P2-15 | Hoje (mobile) | [O] "comparar.Enquanto" | espaço perdido pelo `<br>` oculto | microcopy | P2 | B | correção | espaço explícito | — | — | implementado |
| P2-16 | Detalhe (desktop) | [O] `antes/1280-comparacao` | comparação em coluna única com muito espaço vazio | pouco aproveitamento para comparar | P2 | M | correção visual | tabela compacta de linhas no desktop | — | — | backlog |
| P3-01 | Suporte | — | não há como reportar preço divergente | dado errado persiste | P3 | M | nova funcionalidade | formulário real ou e-mail com destino e triagem | canal de suporte (D-09) | — | backlog |
| P3-02 | Reengajamento | — | sem favoritos ou alertas | retorno depende da pessoa | P3 | A | nova funcionalidade | só com necessidade demonstrada e infraestrutura de envio | backend, consentimento | — | backlog |
| P3-03 | Encartes | [C] `flyerShareUrl` compartilha a imagem da origem | link não reabre o encarte no app | continuidade | P3 | M | fluxo incompleto | `?encarte=id&pagina=n` com fallback "não disponível" | — | — | backlog |
| P3-04 | Lista | — | lista só neste navegador | troca de aparelho perde a lista | P3 | A | nova funcionalidade | exportar/compartilhar lista por link, sem conta | — | — | backlog |

## 6. Melhorias implementadas

### 6.1 Confiança nos preços e na localização
- **Plausibilidade** (`lib/comparison.ts`, `lib/deals.ts`): diferença ≥3× entre redes para o mesmo produto
  tira o item do destaque, remove a economia, o "menor preço" e o preço por kg/L, e mostra aviso.
- **Rótulos com escopo** (`lowestPriceLabel`): único, empate, filtros ativos, condição.
- **Alcance do preço** (`store-location.tsx`, `store-contact.tsx`, `product-card.tsx`): "Preço do site";
  "não confirmado em uma unidade física"; filial só com referência escolhida pela pessoa, sempre "em linha
  reta, não é o trajeto".
- **Condições** (`lib/domain.ts`): "Só para membros do PinClube", "Exige cupom", "Levando n un. ou mais";
  a mesma frase vai para o texto compartilhado.
- **Idade da informação**: "visto hoje às 12:03" nos cartões, na lista e nas linhas; "Dados publicados…" na
  cobertura; por rede, preços atuais e última observação.
- **Preços fora da comparação** com motivo (futura, vencida, desatualizada, indisponível).
- **Encartes sem data final** sem promessa de validade.

### 6.2 Hierarquia do cartão
Antes: foto, nome, embalagem em gramas, preço, rede, **endereço de filial arbitrária**, distância, condição,
"N preços / Também R$ x" (rede em tooltip), ações, aviso de preço online em 10 px.
Depois: foto, nome, embalagem legível, preço (+ preço por kg/L quando comparável), desconto, **condição logo
abaixo do preço**, rede, "Preço do site · visto …", local (unidades ou distância com referência),
comparação com a rede escrita (ou aviso de diferença incomum), ações ("Onde encontrar", compartilhar,
adicionar com "✓ n"). O nome acessível inclui preço, rede e condição.

### 6.3 Estados e continuidade
- `StatusPanel` (erro, offline, vazio) em Hoje, Buscar, Encartes e detalhe; banners só onde não há painel.
- `lib/snapshot.ts`: mensagens por causa; "Tentar novamente" refaz a consulta sem recarregar.
- Falha de atualização com dados: aviso com horário dos dados carregados.
- Carregamento sem zeros; link compartilhado com "Abrindo o produto do link…".
- Histórico: produto como entrada do histórico (`?produto=`), Voltar do navegador fecha, rolagem e foco voltam
  ao cartão; foco no título ao abrir; atalho "Ir para o conteúdo".
- Busca: relevância com termo, contagem, ordem visível, chips de filtros removíveis, vazios distintos,
  botão para limpar o termo, "Fim dos resultados."
- Lista: desfazer persistente (unitário e em lote), avisos de armazenamento persistentes, cópia de valor
  ilegível (`med-list-*-copia-<hash>`), quantidade anunciada, nomes sem duplicação, estados por item.
- Estimativa por rede: total × subtotal parcial, aviso de nenhuma rede completa.

### 6.4 Acessibilidade e visual
Tokens `--muted` (#5b6c62) e `--focus` (#173d30); `.notice.amber` com cor de alerta; tamanhos mínimos para
informação de decisão; menu desktop sem quebra a 768 px; `aria-current`, `aria-pressed`, `aria-expanded`,
`role="status"` na contagem; "(abre em nova aba)" nos links externos; foto do cartão decorativa.

### 6.5 Arquivos
Novos: `lib/format.ts`, `lib/comparison.ts`, `lib/list-storage.ts`, `lib/snapshot.ts`,
`components/status-panel.tsx`, `components/offer-row.tsx` (linha extraída de `market.tsx`),
`components/sources.tsx`, testes `lib/{format,comparison,list-storage,deals,domain}.test.ts`.
Alterados: `components/market.tsx`, `product-card.tsx`, `product-range-card.tsx`, `store-location.tsx`,
`store-contact.tsx`, `store-estimates.tsx`, `offer-share.tsx`, `price-input.tsx`, `flyers.tsx`,
`flyer-stories.tsx`; `lib/domain.ts` (só `conditionLabel`), `lib/deals.ts`, `lib/filters.ts`, `lib/search.ts`,
`lib/flyers.ts` e seus testes; `app/globals.css`; documentação.

**Preservados:** endpoints (`/api/public`, `/api/location`, `/api/location/reverse`), chaves de
armazenamento (`med-list-*`, `med-nearby-*`, `med-region`), parâmetros de link (`produto`, `oferta`,
`regiao`), `rankOffers`, `offerState`, `basket`, `exactMatch`, `unitPrice`, `isConditional`, `flyerState`,
separação real/demo, stack e navegação. **Mudanças deliberadas de regra de apresentação:** guarda de
plausibilidade no destaque, textos de condição, rótulos de encarte sem data final, ordem por relevância
(nova opção, padrão só com termo) e ordem da faixa Hoje (reuso da ordem "maior desconto e mais perto").

### 6.6 Capturas comparativas
Mesmos dados, relógio e larguras nos dois lados (antes/depois); método em
[auditoria-ux-capturas.md](auditoria-ux-capturas.md). As imagens não foram mantidas no repositório; as telas
comparadas foram: Hoje (390/1280 px), API indisponível, sem conexão, busca "leite integral", busca sem
resultado por filtros, detalhe do produto (390 px), comparação suspeita (1280 px), onde encontrar, tamanhos,
lista e estimativa (1280 px), lista após remover, lista ilegível no armazenamento, preço antigo (demo), foco
do teclado, cabeçalho a 768 px e timeout da API.

## 7. Validação

Ver [VALIDACAO.md](VALIDACAO.md) (seção de 27/09/2026) para comandos, resultados e limitações.

## 8. Backlog e dependências não implementadas

| ID | Tema | Por que não foi feito na UI | Proposta / contrato necessário |
|---|---|---|---|
| D-01 | Correspondência de produtos | a regra vive no ETL (`match_products`); mudar na UI mudaria equivalência | não juntar nome sem tamanho, ou vendido por peso ("Kg"), a grupo com tamanho quando a razão de preço for implausível; trazer por oferta o nome e a embalagem da fonte (`source_name`, `amount`, `unit`, `sold_by_weight`) para a UI mostrar a embalagem de cada rede |
| D-02 | Filiais inconsistentes | dado de origem | validar cidade/UF do endereço contra as coordenadas (ex.: "Atacadão - Curitiba", PR, com coordenadas em Fortaleza; "Praia do Preá - Cruz/CE" com coordenadas da Beira-Mar; "Coco" do Pão de Açúcar a ~300 km) |
| D-03 | Abrangência do preço | o snapshot só tem preço de site por rede (`context_id` = rede) | campo `scope` por oferta (site, todas as lojas, lojas específicas) quando a fonte informar |
| D-04 | Promoção por quantidade | "Leve 3 e pague 2", "2 un por R$ x" só em `deal_label` | estruturar em `conditions.min_quantity` e preço por unidade na promoção |
| D-05 | Cobertura | `coverage.offers` conta variantes de clube e preços antigos | enviar contagens de preços atuais ou manter o cálculo no cliente (feito) |
| D-06 | Contato | 0 telefones no snapshot | `retailer_locations[].phone` |
| D-07 | Atualidade por rede | só há `price_observed_at` e `generated_at` | `last_success_at` por rede para distinguir coleta, observação e publicação |
| D-08 | Administração | API sem sessão (501) | esconder `/admin` ou implementar sessão real; a confiabilidade hoje é garantida pelo gate de `refresh.py`/`publish.py` |
| D-09 | Reportar preço | não há destino | canal com triagem (e-mail do projeto ou endpoint); não criar formulário sem destino |
| D-10 | Desktop | escopo | tabela compacta de comparação ≥1024 px (P2-16) |
| D-11 | Encarte por link | escopo | P3-03 |
| D-12 | Offline | política atual: preços ocultos | decidir com pessoas se a lista deve mostrar a última consulta com data quando sem sinal no mercado [H] |
| D-13 | Documentação de `web/` | fora do escopo do código | atualizar `README.md`, `INTEGRACAO.md` e `ALTERACOES.md` para a stack Vite atual |
| D-14 | Tamanho de `market.tsx` | a auditoria manteve a estrutura de estado (1.508 → 1.832 linhas, com linha de comparação e fontes extraídas) | extrair resultados da busca e Minha lista em componentes próprios, com o estado ainda em `Market` |
