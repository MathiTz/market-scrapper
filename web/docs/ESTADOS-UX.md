# Jornada e matriz de estados — Mercado em Dia

Complemento de [AUDITORIA-UX.md](AUDITORIA-UX.md). Base: `main` @ `12e46d0` (antes) e branch local
`ux/auditoria-experiencia` (depois), com a mesma cópia congelada do snapshot público de 27/09/2026 e relógio
fixo em 27/09/2026 18:00 (Fortaleza). Método das capturas: [auditoria-ux-capturas.md](auditoria-ux-capturas.md)
(imagens não mantidas no repositório).

Legenda de evidência: **[O]** observado na interface executada (captura ou medição), **[C]** lido no código,
**[H]** hipótese a validar com pessoas ou em aparelho real.

## 1. Mapa da jornada

| Etapa | Intenção | Entrada | Tela / componente | Ação | Feedback | Saída | Estados alternativos | Persistência | Dependência técnica |
|---|---|---|---|---|---|---|---|---|---|
| Primeiro acesso | "O que está em oferta hoje?" | `/` direto ou busca web | Hoje (`market.tsx`) | ler ofertas, rolar faixa | carregamento textual, faixa de cartões, cobertura | cartão → produto; busca | carregando, erro de API, offline, snapshot vazio | nenhuma | `GET /api/public` (snapshot inteiro, ~5,4 MB sem compressão) |
| Retorno | continuar a lista, ver o que mudou | `/` | Hoje, Minha lista | abrir lista | contagem no menu, itens salvos | estimativa por rede | lista ilegível, armazenamento bloqueado | lista em `localStorage` (`med-list-real`/`med-list-demo`), local em `sessionStorage` (`med-nearby-*`) | navegador |
| Link compartilhado | ver a oferta recebida | `/?produto=&oferta=&regiao=` | detalhe do produto | ler, comparar | "Oferta compartilhada" na linha; aviso se não estiver atual | lista, loja, site | produto removido, oferta não atual, oferta de clube (liga "incluir condições") | URL | IDs estáveis `produto-rede` gerados em `services/public_api.py` |
| Entender a proposta | "posso confiar?" | Hoje | cobertura, "Como ler os preços", redes | ler | contagens, horário da publicação, por rede: preços atuais e última observação | — | carregando, erro | — | campos `generated_at`, `ttl_hours`, `last_error` |
| Definir local | ver lojas perto | "Perto de você" | `nearby-filter.tsx` (diálogo) | GPS por clique ou endereço digitado; raio 2/5/10/20 km | sugestões, mensagens de erro específicas | cartões e comparação com distância em linha reta | GPS negado, sem suporte, sem HTTPS, impreciso (>2 km); endereço sem resultado; serviço lento | `sessionStorage` | `POST /api/location`, `GET /api/location/reverse` (Photon/OSM) |
| Trocar região | outra cidade | cabeçalho | — | — | — | — | não aplicável: o snapshot tem só `regions: ["Fortaleza"]` | `med-region` (legado) | — |
| Descobrir (Hoje) | achar ofertas úteis | Hoje | `offer-rail.tsx`, `product-card.tsx` | deslizar, abrir, adicionar | ordem por maior desconto informado; destaque de economia entre redes | detalhe, lista | nenhum preço no raio; offline; erro | — | `regular_price_cents`, `deal_label` |
| Buscar | achar um produto | caixa de busca (dock no mobile) | Buscar | digitar | contagem de resultados, ordenação visível | detalhe, cartão de tamanhos | sem resultado para o termo; sem resultado por filtros; por raio; carregando; erro | estado em memória (não na URL) | busca local por prefixo de palavra, sem acentos (`lib/search.ts`) |
| Filtrar e ordenar | reduzir a lista | "Filtros" | painel de filtros, chips ativos | redes, desconto, faixa de preço, condições, sem preço atual | chips removíveis, contagem no botão | resultados | filtros excluem tudo | memória | `lib/filters.ts` |
| Encartes | consultar o encarte da rede | Encartes | `flyers.tsx`, `flyer-stories.tsx`, `flyer-player.tsx` | escolher rede/período, abrir leitor, ampliar, baixar, compartilhar | página x/y, contagem regressiva, pausa | site oficial, arquivo original | sem encarte no filtro; imagem indisponível; PDF; arquivo vencido | — | `flyers[].media_pages` (imagens na origem da rede) |
| Avaliar no cartão | decidir se vale abrir | qualquer lista | `product-card.tsx` | ler | preço, condição, rede, horário, local | detalhe, lista, "Onde encontrar" | sem foto, sem preço, preço oculto offline, diferença incomum entre redes | — | — |
| Comparar | "onde está mais barato?" | cartão | detalhe (`market.tsx`, `offer-row.tsx`) | ler linhas, incluir condições | menor preço (ou único, ou empate), condição, horário, estoque informado | site da loja, lista, "Onde encontrar" | uma única oferta; empate; condição incluída; preços fora da comparação; diferença incomum; fora do raio | memória + URL `?produto=` (depois) | agrupamento por nome e tamanho no ETL (`match_products`) |
| Tamanhos | escolher embalagem | cartão de faixa | `product-range-card.tsx` | abrir diálogo, escolher | preço por kg/L/un. e "Menor preço por …" | detalhe, lista | tamanho sem preço; unidades diferentes (g vs un.) | — | `lib/group.ts` |
| Onde encontrar | ir a uma loja | botão no cartão/linha | `store-location.tsx` | ler, abrir mapa | alcance do preço, unidade mais próxima (com referência) ou número de unidades | Google Maps (nova aba) | sem referência; sem endereço cadastrado; demo (fictício) | — | `retailer_locations` |
| Adicionar à lista | planejar | "+" no cartão, detalhe, caixa da lista | `list-adder.tsx`, cartões | adicionar | aviso com o nome do produto; "✓ n" no cartão | Minha lista | já na lista (soma 1); máximo 999 | `localStorage` | — |
| Editar a lista | ajustar | Minha lista | itens | +/−, remover, desfazer | quantidade anunciada, aviso "Desfazer" persistente | estimativa | item sem preço; produto fora do catálogo; offline | `localStorage` | — |
| Estimar por rede | "onde a lista sai mais barata?" | Minha lista | `store-estimates.tsx` | abrir cada rede | total ou subtotal parcial rotulado; itens sem preço | — | nenhuma rede completa; sem preço; offline | derivado | `basket()` em `lib/domain.ts` |
| Sair para a loja | aproveitar a oferta | "Ver no site da loja", mapa, telefone | linha da comparação, diálogo | abrir destino | "(abre em nova aba)" para leitor de tela | site da rede / mapa | fonte sem URL; demo | — | `source_url` (às vezes é a página geral de ofertas, não a do produto) |
| Compartilhar | mandar para alguém | botão compartilhar | `offer-share.tsx`, leitor de encartes | compartilhar | compartilhamento nativo; senão "Link copiado"; senão campo com o link | app de mensagens | cancelado (silencioso, correto); sem clipboard | URL | Web Share / Clipboard |
| Voltar | retomar o contexto | botão Voltar do app ou do navegador | detalhe | voltar | mesma posição e foco no cartão aberto (depois) | lista anterior | aberto por link (sem histórico anterior) | `history` | — |
| Suporte | reportar preço divergente | — | — | — | — | — | **ausente**; sem canal de suporte no produto | — | exige canal/endpoint (backlog) |
| Reengajamento | ser avisado | — | — | — | — | — | favoritos/alertas **ausentes** por decisão; sem conta nem push | — | exige backend e consentimento (backlog) |
| Offline | consultar sem sinal | qualquer tela | PWA básico (`public/sw.js`) | — | aviso de conexão; preços ocultos; lista mantida | — | sem dados carregados; retomada | lista local | service worker só guarda `offline.html` e ícone |

## 2. Matriz de estados e transições

Cada linha: **Antes** (commit `12e46d0`) → **Depois** (branch). "Aceite" é o critério verificável.

### 2.1 Sistema e dados

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Primeiro carregamento | Hoje, Buscar, Encartes | abrir o site, snapshot a caminho | [O] texto "Consultando ofertas…"; cobertura mostrava **"0 redes · 0 produtos · 0 ofertas atuais"**; encartes e fontes vazios | [O] "Carregando as ofertas publicadas…", "Carregando a cobertura…", "Carregando encartes…"; Encartes com carregamento próprio | automática | `role="status"` no carregamento | nenhum zero exibido antes de os dados chegarem |
| Link compartilhado carregando | Buscar | `/?produto=` | [O] "Buscando no catálogo…" genérico | "Abrindo o produto do link…" | automática | `role="status"` | texto específico enquanto carrega |
| Sucesso | todas | 200 com dados | [O] correto | [O] correto + "Dados publicados hoje às 12:04" | — | — | horário de publicação visível na cobertura |
| Atualização em segundo plano falhou | todas | refetch com erro e dados já carregados | [C] nenhum aviso (`market.tsx:224-230`): dados antigos sem indicação | aviso "Não foi possível atualizar os preços agora. Você está vendo os dados carregados …" + "Tentar novamente" | refetch sem recarregar a página | `role="status"` | aviso aparece e some após refetch bem-sucedido ([C]; não reproduzido por captura) |
| API indisponível (503/500) | Hoje | sem dados | [O] **"Ainda não temos preços validados para comparar"** + cobertura zerada | [O] painel "Não foi possível carregar as ofertas", mensagem da API, "Nada foi perdido: sua lista continua salva", "Tentar novamente", "Abrir minha lista"; cobertura oculta | refetch (antes: `location.reload()`) | aviso com `role="alert"` só onde não há painel | nenhuma tela diz "sem ofertas" quando a API falhou |
| API indisponível | Buscar | sem dados | [O] **"Nenhum produto encontrado. Tente outro nome…"** | [O] mesmo painel de erro | idem | idem | idem |
| API indisponível | Encartes | sem dados | [C] "Nenhum encarte neste filtro" | painel de erro | idem | idem | idem |
| API indisponível | Minha lista | sem dados | [C] itens "Sem preço atual nas lojas consultadas" | itens "Preço indisponível no momento"; aviso no topo | lista intacta | `role="alert"` | nenhum item marcado como "sem preço" por falha |
| Demora / timeout | todas | API não responde (15 s, 1 nova tentativa) | [O] mensagem técnica do navegador exibida ao consumidor (ver `estado-timeout`) | [O] "A consulta das ofertas demorou mais que o esperado." | "Tentar novamente" | idem | nenhuma mensagem técnica em inglês |
| Resposta malformada | todas | JSON inválido | [C] mensagem técnica do parser | "Os dados recebidos das ofertas estão incompletos." | idem | idem | idem |
| Snapshot vazio | Hoje | 200 sem produtos | [O] "Estamos conferindo as fontes…" (correto), texto colado "comparar.Enquanto" | [O] mesmo estado, espaço corrigido, "Ainda não há preços atuais publicados" | encartes seguem disponíveis | — | estado só aparece com dados carregados e vazios |
| Offline com dados | Hoje | `navigator.onLine=false` | [O] **"Ainda não temos preços validados…"** ao lado de "4773 ofertas atuais" | [O] painel "Você está sem conexão. Os preços ficam ocultos até a conexão voltar… Sua lista continua salva" | volta sozinho ao reconectar | `role="status"` | nenhuma contradição entre painel e cobertura |
| Offline com dados | Buscar / detalhe / lista | idem | [O] cartões "Sem preço atual"; detalhe com área vazia; estimativa "Ainda não há preços atuais" | cartões "Preço oculto sem conexão"; detalhe com painel offline; estimativa "ocultas sem conexão" | idem | idem | o motivo (conexão) aparece onde o preço sumiu |
| Offline sem dados | todas | abriu sem rede | [C] erro de rede do navegador como mensagem | painel de erro "Não foi possível conectar ao serviço de ofertas." + aviso offline; `offline.html` quando a navegação falha (SW) | recarregar ao voltar | idem | idem |
| Retomada da conexão | todas | evento `online` | [C] preços voltam sem aviso | aviso breve "Conexão de volta. Os preços voltam a aparecer." (informação não crítica) | React Query refaz a consulta se estiver velha (>60 s) | `role="status"` | preços reaparecem sem recarregar ([O] cenário `conexao`) |
| Dados antigos preservados após falha | todas | falha de refetch | [C] preservados, sem aviso | preservados, com aviso e horário | — | — | idem acima |

### 2.2 Localização

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Região não escolhida | cabeçalho | 1 região no snapshot | [O] `<select>` com uma única opção | rótulo fixo "Fortaleza CE" ("Cobertura: Fortaleza") | — | texto lido como cobertura | não há controle sem efeito |
| Região de link inválida | cabeçalho, compartilhar | `?regiao=Recife` | [C] estado aceitava qualquer texto | usa só regiões presentes no snapshot | — | — | cabeçalho nunca mostra região não coberta |
| Sem referência de local | cartões, "Onde encontrar", lista | padrão | [O] **endereço de uma filial escolhida pelo centro de Fortaleza** exibido como "a loja" da oferta | [O] "19 unidades · defina seu local para ver a distância"; diálogo explica que o preço é do site | "Perto de você" | — | nenhum endereço de filial sem referência escolhida pela pessoa |
| Edição manual | diálogo | digitar ≥3 letras | [O] sugestões com atraso de 350 ms, lista fixa | inalterado | `sessionStorage` | `aria-live` nas sugestões | — |
| Endereço sem resultado | diálogo | Photon sem resultados | [C] mensagem específica | inalterado | tentar outro termo | `role="status"` | — |
| Consulta em andamento / demora | diálogo | busca de endereço | [C] "Buscando…", timeout 15 s com mensagem | inalterado | — | `aria-busy` | — |
| GPS negado | diálogo | permissão recusada | [O] "Localização não autorizada. Você pode digitar seu endereço…" | inalterado | campo de endereço | mensagem em `role="status"` | — |
| GPS sem suporte / sem HTTPS / impreciso | diálogo | — | [C] mensagens específicas (>2 km = impreciso) | inalterado | endereço | — | — |
| Localização confirmada | cartões, detalhe | ponto + raio | [O] "≈ 2,3 km de você" | "≈ 2,3 km da sua referência · unidade Rui Barbosa"; detalhe "unidade mais próxima ≈ x km"; diálogo "em linha reta, não é o trajeto" | "×" remove | — | distância sempre como linha reta, com a unidade nomeada |
| Nenhum mercado no raio | Hoje, Buscar | filtro sem ofertas | [O] "Nenhuma oferta neste raio" + remover filtro | inalterado (Buscar ganhou "Ver em todas as lojas") | remover filtro | — | — |
| Rede sem endereço cadastrado | filtro de raio | Centerbox (0 unidades) | [C] contagem "oferta(s) sem localização conferida" | "n preços de redes sem endereço cadastrado ficaram fora do filtro" | — | — | exclusão explicada |
| Mudança de local com lista | lista | trocar referência | [C] estimativa recalculada (ofertas dentro do raio) | inalterado + "unidade mais próxima ≈ x km" por rede | — | — | — |
| Endereço de filial inconsistente | dados | ex.: "Atacadão - Curitiba" com coordenadas em Fortaleza | [O] nos dados (não tratável na UI) | documentado no backlog (dados) | corrigir sincronização de filiais | — | — |

### 2.3 Busca e filtros

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Busca inicial vazia | Buscar | sem termo | [O] "Produtos monitorados", ordem por desconto sem aviso | contagem + "Ordenar por" visível + dica para desempatar pela distância | — | contagem em `role="status"` | ordem ativa sempre visível |
| Digitando / processando | Buscar | debounce 220 ms | [O] "Filtrando…" | idem; contagem "Atualizando resultados…" | — | idem | — |
| Resultados | Buscar | termo com correspondência | [O] **"leite integral" → "Leite de Coco…" primeiro** (maior desconto) | [O] "Mais relevantes" por padrão com termo: nome que começa pelo termo, frase, primeira palavra | trocar ordem | — | termo exato antes de descontos quando há busca |
| Um só resultado | Buscar | — | [C] sem contagem | "1 produto" | — | — | — |
| Nenhum resultado para o termo | Buscar | nada corresponde | [O] "Nenhum produto encontrado… A cobertura ainda está sendo validada." | "Nenhum produto encontrado para “x”", dica de grafia e de prefixo | "Limpar busca" | — | termo citado; ação limpa só o que é preciso |
| Nenhum resultado por filtros | Buscar | termo encontra, filtros excluem | [O] mesma mensagem genérica | "Nenhuma oferta com estes filtros · n produtos correspondem à busca sem os filtros ativos" | "Remover filtros" | — | distingue termo de filtro |
| Filtros aplicados | Buscar | redes, desconto, preço, condições | [O] só visíveis com o painel aberto | chips removíveis + contagem no botão "Filtros" (`aria-expanded`) | remover um a um ou "Limpar filtros" | chip com nome acessível "Remover filtro: …" | filtros ativos visíveis com o painel fechado |
| Limpar tudo | Buscar | — | [C] "Limpar filtros" só no painel | também nos chips; limpa categoria, condições e "sem preço atual" | — | — | — |
| Produto só com preço antigo | Buscar | todas as ofertas vencidas/desatualizadas | [O] **inalcançável**: a opção "Incluir produtos sem preço atual" nem aparecia (`market.tsx:418`) | [O] opção aparece; produto listado como "Sem preço atual" | — | — | produto com preço antigo pode ser encontrado |
| Fim da lista | Buscar | todos carregados | [C] sem marcação | "Fim dos resultados." (listas longas) | — | — | — |
| Consulta substituída | Buscar | novo termo | [C] reinicia paginação | inalterado | — | — | — |
| Voltar da comparação | Buscar → detalhe → voltar | botão do app ou do navegador | [O] botão do app voltava sem restaurar rolagem nem foco; **botão do navegador saía da busca** | mesma posição, foco no cartão aberto; botão do navegador fecha o produto | `history.pushState` com `?produto=` | foco devolvido | voltar preserva termo, filtros, rolagem e foco |

### 2.4 Produto e oferta

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Imagem ausente ou quebrada | cartão, detalhe | `image_url` nulo ou erro | [O] "Sem foto"/"Sem imagem" (9–11 px, contraste 3,7–4,0:1) | mesmo comportamento, 11–12 px, contraste ≥ 4,9:1 | — | foto do cartão é decorativa (`alt=""`), nome no botão | texto legível |
| Nome longo | cartão | até 126 caracteres | [O] quebra sem truncar | inalterado (sem corte de informação) | — | — | sem rolagem horizontal ([O] 0 px) |
| Preço ausente | cartão, detalhe | sem preço atual | [O] "Sem preço atual" | idem; detalhe mostra preços fora da comparação com motivo | — | — | — |
| Embalagem incompleta | cartão, detalhe | tamanho não reconhecido (166 produtos "1 un") | [O] "1 un"; detalhe "1 embalagem · 1 un" e preço "/un." | "Tamanho não informado"; sem preço por unidade | — | — | nenhum preço por unidade calculado sem tamanho |
| Tamanho em gramas | cartão, detalhe | ex.: 18000 g | [O] "18000 g", "1 embalagem · 600 g" | "18 kg", "600 g", "12 × 350 ml", "48 unidades" | — | — | — |
| Uma única oferta | detalhe | 1 preço (≈98% dos produtos) | [O] **"Menor preço encontrado entre as ofertas monitoradas"** | "Único preço atual entre as ofertas monitoradas" | — | — | "menor" só com duas ou mais |
| Múltiplas ofertas | detalhe | ≥2 | [O] rótulo na primeira | "Menor preço…" (+ "com os filtros atuais" quando há raio/rede) | — | — | afirmação limitada aos filtros |
| Empate | detalhe | mesmo menor preço | [C] rótulo só na primeira linha | "Empate no menor preço…" em todas as empatadas | — | — | — |
| Oferta futura / vencida / desatualizada / indisponível | detalhe | `offerState` ≠ current | [C] sumia sem explicação | "n preços fora da comparação" com motivo: futura (data), vencida (data), desatualizada (visto em … não confirmado nas últimas 36 h), indisponível | — | `<details>` nativo | vencida ≠ desatualizada no texto |
| Estoque | detalhe | `stock` informado / desconhecido | [O] "Disponível na consulta da fonte" / "Disponibilidade desconhecida" | "Disponível no site na última consulta · Estoque informado pela loja: n" / "Estoque não informado pela fonte" | — | — | nenhum "em estoque" garantido |
| Condição de clube | cartão, detalhe, compartilhar | `conditions.club` | [O] "Clube PinClube", **"Clube Clube"** (Centerbox) | "Só para membros do PinClube", "Só para membros do clube da loja"; no cartão, logo abaixo do preço; na linha do menor preço "(com condição)" | — | condição no nome acessível do cartão | nenhum preço de clube sem "Só para membros" |
| Cupom, mínimo, limite, pagamento | idem | outros campos de `conditions` | [C] "Cupom X", "Mínimo 2 un." | "Exige cupom X", "Levando 2 un. ou mais", "Limite de n por cliente" | — | — | — |
| Promoção por quantidade só no rótulo | cartão | ex.: "Leve 3 e pague 2" em `deal_label` | [O] selo junto ao preço (preço é o de 1 unidade) | inalterado; registrado no backlog (dados não trazem `min_quantity`) | — | — | — |
| Fonte com última coleta falha | fontes | `last_error` | [O] "Fonte temporariamente indisponível" | "A última coleta teve problema; mantida a lista anterior" | — | — | — |
| Filial sem confirmação de preço | cartão, diálogo | preço do site | [O] "Localização da loja" com endereço e "Abrir no mapa" | "Onde encontrar": "Preço do site da rede… não foi confirmado em uma unidade física" antes de qualquer endereço | — | "(abre em nova aba)" | alcance do preço dito antes da unidade |

### 2.5 Comparação

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Equivalente confirmado | detalhe | mesmo produto em ≥2 redes (92 produtos) | [O] linhas por preço | idem + resumo "Menor preço atual: R$ x no Y · n preços" no topo | — | link "Ver comparação" | preço visível na primeira tela do mobile |
| Diferença implausível | Hoje, cartão, detalhe | razão ≥ 3× (4 de 92: laranja 18 kg, presunto kg, cenoura kg, pimentão kg) | [O] **"R$ 45,10 a menos" e R$ 0,04/kg como oferta do dia** | fora do destaque; cartão "Preços muito diferentes entre redes: confira a embalagem"; detalhe explica e oculta preço por kg/L | origem pelo link | aviso `role="note"` | nenhuma economia anunciada entre preços 3× distantes |
| Alternativa não equivalente | detalhe | mesma subcategoria | [O] "Não entram na comparação exata" | "São produtos diferentes: não entram na comparação acima." | — | — | — |
| Diferença de embalagem | cartão de faixa | tamanhos do mesmo produto | [O] "R$ 4,29 – R$ 7,97" sem dizer de qual tamanho; linhas fora de ordem | "a partir de R$ 4,29 na embalagem de 600 ml"; "Menor preço por L: R$ 5,31/L (1,5 L)"; linhas por tamanho | — | nome acessível com tamanhos | "a partir de" sempre com o tamanho |
| Oferta condicionada incluída/excluída | detalhe | checkbox | [O] checkbox sempre visível | só quando há preço com condição, com contagem "(n disponíveis)" | — | — | — |
| Sem preço atual | detalhe | nenhum preço vigente | [O] "Sem oferta atual" | idem + preços fora da comparação abertos | — | — | — |
| Economia não calculável | cartão | 1 rede | [C] sem economia | inalterado | — | — | — |
| Ranking alterado por região | detalhe | raio | [O] "n outras opções fora deste filtro" | inalterado | "Ver preços em todas as lojas" | — | — |

### 2.6 Lista

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Lista vazia | Minha lista | sem itens | [O] "Comece sua lista de consulta." | inalterado | — | — | — |
| Item adicionado | qualquer | "+" | [O] aviso "Adicionado à sua lista" (sem nome) | "“Nome” adicionado à lista"; cartão passa a "✓ 1" | `localStorage` | `role="status"`; botão "Adicionar mais 1 de … (n na lista)" | nome do produto no aviso |
| Item já existente | qualquer | "+" de novo | [O] mesmo aviso | "Agora são 2 de “Nome” na lista" | — | idem | — |
| Quantidade alterada | lista | +/− | [O] número sem anúncio | número em `aria-live` | — | "Quantidade: n" | — |
| Remoção e desfazer | lista | "×" ou "Remover esses itens" | [O] **remoção imediata, sem desfazer** | aviso persistente "“Nome” foi removido da lista. Desfazer" (sem tempo limite) | desfazer restaura a lista anterior | `role="status"` | desfazer disponível até a próxima alteração ([O] cenário `remocao`) |
| Lista carregada do armazenamento | lista | retorno | [O] 3 itens após recarregar | inalterado ([O]) | — | — | — |
| Falha ao salvar | lista | `setItem` recusado | [C] aviso temporário de 2,8 s | aviso persistente na lista | tenta de novo a cada alteração | `role="status"` | informação crítica não depende de aviso temporário |
| Armazenamento bloqueado | lista | `localStorage` lança erro | [C] lista vazia, sem explicação | "Este navegador não permite guardar dados neste site…" | — | idem | — |
| Armazenamento corrompido | lista | valor ilegível | [O] **sobrescrito por `[]` sem aviso** | cópia do valor original em `med-list-real-copia-<data>` + aviso | "Entendi" | idem | nada apagado sem cópia ([C] testado em `list-storage.test.ts`) |
| Produto removido do catálogo | lista | `product_id` sem produto | [C] "Sem preço atual…" | "Este produto não está mais entre as ofertas monitoradas" | remover | — | — |
| Preço alterado / vencido | lista | referência mudou | [C] recalculado a cada carga | idem + "visto hoje às …" | — | — | — |
| Cobertura parcial | estimativa | rede sem todos os itens | [O] subtotal com o mesmo destaque de um total | "Subtotal parcial", cor atenuada, "faltam n itens", itens "não somado" | — | — | parcial nunca parece total |
| Nenhuma rede completa | estimativa | todas parciais | [O] cinco subtotais parciais sem aviso | "Nenhuma rede tem preço atual para todos os n itens… não devem ser comparados entre si." | — | `role="note"` | aviso sempre que nenhuma rede cobre a lista |

### 2.7 Encartes

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Nenhum encarte | Encartes, Hoje | filtro vazio / nenhum vigente | [O] Encartes com mensagem; Hoje com seção vazia | Hoje: "Nenhum encarte dentro da validade publicado agora." | outra rede/período | — | seção nunca vazia sem texto |
| Carregamento | Encartes | snapshot a caminho | [C] abas e mensagem "Nenhum encarte…" durante a carga | "Carregando os encartes…" | — | `role="status"` | — |
| Leitura, zoom, pausa, primeira/última página | leitor | abrir | [O] 25–150 %, pausa, setas, teclado, respeita movimento reduzido | inalterado | — | anel de foco visível (antes 2,1:1) | — |
| Sem data final | cartão, leitor | Centerbox/Frangolândia (quando publicados) | [C] "Dentro da validade" / "Em vigor" sem data de fim | "Publicado, sem data final" / "Data final não informada" | — | — | nenhuma promessa de validade sem data |
| Validade encerrada | arquivo | vencido | [O] "Vencido", arquivo por mês/semana | inalterado | — | — | — |
| Imagem/PDF indisponível | cartão, leitor | erro de carga | [C] "Imagem indisponível · consulte a origem" | inalterado | site oficial | — | — |
| Link compartilhado de encarte | compartilhar | — | [C] compartilha a URL da imagem na origem da rede, não reabre no app | inalterado; backlog | — | — | — |

### 2.8 Compartilhamento e ações externas

| Estado | Tela | Entrada / condição | Antes | Depois | Recuperação e persistência | Acessibilidade | Aceite |
|---|---|---|---|---|---|---|---|
| Nativo disponível | cartão, linha, diálogo | `navigator.share` | [C] texto com preço, rede, canal, condição e horário | condição com "Só para membros…" | — | — | condição acompanha o compartilhamento |
| Nativo indisponível | idem | sem Web Share | [C] copia o link; "Link copiado para compartilhar." | inalterado | — | `role="status"` | — |
| Cópia falhou | idem | clipboard recusado | [C] campo com o link | inalterado | — | — | — |
| Cancelamento | idem | `AbortError` | [C] silencioso (correto) | inalterado | — | — | cancelar não é erro |
| Link inválido / oferta removida | detalhe | `?produto=` inexistente | [O] "Produto compartilhado não encontrado." | explica por que e sugere buscar | — | `role="status"` | — |
| Oferta não atual | detalhe | `?oferta=` fora do ranking | [O] "Esta oferta não está disponível no momento." | "O preço deste link não está mais atual. Veja abaixo os preços atuais deste produto." | — | idem | — |
| Destino externo | linha, diálogo | site da loja, mapa | [O] "Ver origem" | "Ver no site da loja", "Abrir no mapa", "Procurar unidades no mapa" + "(abre em nova aba)" | a aba do app fica intacta | — | destino nomeado |
| Fonte sem URL | fontes | `official_url` vazio (Carnaúba) | [O] link para a própria página | sem link | — | — | — |

### 2.9 Interações

| Componente | Estados cobertos (depois) | Observação |
|---|---|---|
| Botões e links | padrão, hover (primário), foco visível 3 px `--focus` (11:1), desabilitado (`opacity .55`), processando ("Tentando…", "Obtendo localização…") | anel antes #87bd54 (2,1:1, abaixo de 3:1) |
| Chips de categoria | selecionado com cor **e** `aria-pressed` | antes só visual |
| Chips de rede (filtro) | selecionado com cor, borda **e** ícone ✓ | antes só cor/borda |
| Navegação | `aria-current="page"` na aba ativa (desktop e mobile) | — |
| Diálogos (local, tamanhos, onde encontrar, encarte) | `showModal`, Esc fecha, clique no fundo fecha, foco volta ao botão que abriu | "Onde encontrar" ganhou fechar pelo fundo |
| Detalhe do produto | foco no título ao abrir; ao voltar, foco no cartão de origem | antes o foco se perdia no `body` |
| Teclado virtual | não verificável neste ambiente [H] | dock fixo de busca + navegação pode cobrir campos em aparelhos reais |
| Atalho | "Ir para o conteúdo" no início da página | novo |
