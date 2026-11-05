# Integração com o backend

## 1. Fluxo público
O componente central é components/market.tsx. O modo demo usa lib/demo.ts diretamente. Implemente o contrato abaixo e altere app/page.tsx para renderizar <Market /> sem demo. Preserve /demo como referência se desejado, mas nesse caso faça essa página renderizar <Market demo /> diretamente, pois atualmente ela reexporta a raiz.

O ponto de troca é fetch("/api/public?" + params). Pode-se adaptar a URL/resposta ali, criar cliente de API ou encaminhar pelo mesmo domínio. Não existe variável de ambiente de URL de API implementada neste pacote.

### GET /api/public
| Parâmetro | Tipo | Uso |
|---|---|---|
| q | string | Busca |
| region | string | Região, inicialmente Fortaleza |
| network | string | ID da rede ou vazio |
| channel | string | catalog, physical, flyer ou vazio |
| category | string | Categoria ou vazio |

`product.ncm`: string de 8 dígitos ou `null`. A classificação fiscal que o publicador junta do warehouse
  (`services/ncm_index.py`) no momento de publicar; `null` quando o snapshot saiu de uma máquina sem warehouse,
  então o campo é opcional e nada pode depender dele. Com ele, a tela de detalhe monta "Alternativas" por NCM
  **e** subcategoria (as duas), em vez de só a subcategoria; a troca é opt-in (`VITE_ALTERNATIVES_NCM=1`, ou
  `?alternativas=ncm` para comparar na mesma build) e, sem o NCM, o comportamento anterior continua.

`product.category_slug` / `product.category_department`: a categoria do warehouse (árvore Cosmos) para o
  produto, juntada na publicação como o `ncm` (`services/category_index.py`); `null` quando o produto não tem
  nó na taxonomia ou foi raspado depois da última rodada do warehouse; nesse caso sem nó, o
  `category_department` ainda pode vir do NCM (`data/ncm/heading-department.csv`: frutas em Hortifruti,
  fraldas em "Fraldas e Absorventes", ração em "Pet"), enquanto o `category_slug` fica `null`. O
  `department` é o nível que vira chip na tela (os oito departamentos de alimentos, ou o ramo inteiro para
  Higiene e Beleza / Limpeza); o `slug` é a folha. Com o switch ligado (`VITE_CATEGORIES_WAREHOUSE=1`, ou
  `?categorias=warehouse` para comparar na mesma build) os chips vêm desses departamentos presentes no
  snapshot, em vez da lista fixa de `categories`; produto sem departamento continua no `category` por palavra-
  chave e aparece em "Todas" e na busca, nunca num chip chutado.

`product.image_url`: URL absoluta da loja, ou caminho relativo `/images/...` quando a URL da loja morreu
  e o publicador usou a cópia verificada que o warehouse espelha localmente; `null` quando não há nenhuma.
  A UI já aceita os dois (o `src` do `<img>` resolve relativo à origem).

`product.subcategory`: string, pode ser vazia. Tipo mais específico que `category` (ex.: "Hidratante", "Sabonete" em vez de um "Higiene e beleza" compartilhado) - vazio quando o ETL não achou uma palavra específica o bastante (veja `subcategorize()` em `services/public_api.py`). A tela de detalhe usa isso para "Alternativas", caindo de volta para `category` quando vazio.
| conditions | string | true para incluir condições especiais |
| product | string | ID de produto compartilhado ou vazio |

Resposta 200: objeto com products, offers, flyers, retailers, regions, categories, coverage, generated_at.
Contrato exato: tipo Data em components/market.tsx; Product, Offer, Conditions e Flyer em lib/domain.ts.
Exemplo completo e executável: retorno de demoData() em lib/demo.ts.

- products: Product[]; image_url opcional ativa foto, ausência/falha usa fallback; image_source_url registra origem.
- offers: Offer[] relacionados por product_id; preços em CENTAVOS inteiros: 1590 = R$ 15,90.
- flyers: Flyer[]; media_pages contém imagens ordenadas para o leitor.
- retailers: id, name, official_url, audit_status, enabled (número), last_error (string ou null).
- regions e categories: string[].
- coverage: networks, products, offers, exact_pairs (números).
- generated_at: data ISO.
- Erro HTTP não-2xx com objeto {"error":"Mensagem legível"}; a UI trata falha e timeout.

Mantenha IDs estáveis. Datas ISO com fuso; apresentação em America/Fortaleza. published é numérico. Preserve conditions, availability, ttl_hours, datas de observação/validade e collection_error: a interface usa esses campos para excluir ofertas desatualizadas e distinguir condições. Estoque não confirmado não significa disponível.
Retorne somente registros públicos. lib/domain.ts contém regras de apresentação/cálculo e schemas compartilhados, mantidos para preservar comportamento.

## 2. Localização
components/nearby-filter.tsx chama POST /api/location com {"query":"Aldeota, Fortaleza"}.
Resposta 200: {"places":[{"id":"local-1","label":"Aldeota, Fortaleza","latitude":-3.735,"longitude":-38.50}]}.
Erro HTTP não-2xx com {"error":"Mensagem"}. Tipo AddressResult em lib/geocoding.ts.
Substitua a rota 501 pelo serviço real. GPS usa navigator.geolocation; distância usa store_latitude/store_longitude em lib/location.ts. A seleção fica em sessionStorage.

## 3. Lista, links e compartilhamento
Lista em localStorage, sem API: med-list-demo ou med-list-real; região em med-region. Itens: product_id, name, quantity.
Links de oferta usam produto, oferta e regiao; encartes usam flyerShareUrl em lib/flyers.ts. Preserve parâmetros ao integrar domínio e rotas.
Compartilhamento depende de Web Share/clipboard. Download externo depende da origem e do navegador.
Com conta (seção 4), a lista continua em `localStorage` e ganha cópias no servidor: `POST /api/account/lists`
salva a lista atual e `GET /api/account/lists` devolve as listas salvas, que podem ser abertas em outro aparelho.

## 4. Conta do usuário
Cadastro por e-mail e senha, ou Google. A sessão é um cookie `HttpOnly` (`med_session`, `SameSite=Lax`); o
navegador não guarda token em JavaScript. O login com Google nunca vincula automaticamente a uma conta existente
com o mesmo e-mail: quando o e-mail já existe sem vínculo prévio, redireciona para `/conta?erro=google-conta-existente`
sem abrir sessão, exigindo que a pessoa entre pelo método já cadastrado (senha, ou a mesma conta Google se a conta
for só-Google) (prevenindo ataques de pré-sequestro de contas). O local
preferido ("Perto de você") é salvo para a região de navegação ativa (`med-region`, com fallback para `BRAND.city`) e é
aplicado ao abrir `/` apenas quando `preferences.region` coincide com a região atual e não há referência escolhida nesta
aba. A interface e a lista de listas salvas exibem as mensagens de erro retornadas pela API. O login valida o formato do
e-mail e da senha com 400 antes de checar credenciais com 401 genérico ("E-mail ou senha incorretos."), com freio de
10 falhas por 15 minutos por IP+e-mail.

| Rota | Corpo | Resposta |
|---|---|---|
| POST /api/auth/register | `{email, password, name?}` | 201 `{user, preferences}`; 400/409 com `{error}` |
| POST /api/auth/login | `{email, password}` | 200 `{user, preferences}`; 400 formato inválido; 401 genérico; 429 limite de tentativas |
| POST /api/auth/logout | — | 200 `{ok:true}` |
| GET /api/auth/me | — | `{user, preferences, google}`; `user:null` deslogado |
| GET /api/auth/google/start | — | 302 para o Google; 503 sem `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` |
| GET /api/auth/google/callback | `?code&state` | 302 para `/conta?entrou=google` ou `/conta?erro=...` (inclui `erro=google-conta-existente`) |
| GET /api/account/preferences | — | `{preferences:{region, location}}`; 401 sem sessão |
| PUT /api/account/preferences | `{region, location}` | `{preferences}`; 400 se o local for inválido |
| GET /api/account/lists | — | `{lists:[{id,name,lines,created_at,updated_at}]}` |
| POST /api/account/lists | `{name, lines}` | 201 `{list}`; 409 acima de 20 listas |
| PUT /api/account/lists/:id | `{name, lines}` | `{list}`; 404 se não for da conta ou se o ID for malformado (não-UUID) |
| DELETE /api/account/lists/:id | — | `{ok:true}`; 404 se não for da conta ou se o ID for malformado (não-UUID) |

`location` é `null` ou `{label, latitude, longitude, radius_km}` (raio inteiro de 1 a 50 km). `lines` é a mesma
lista do `localStorage`: `[{product_id, name, quantity, checked}]`, até 200 itens. Erros sempre vêm como
`{"error":"Mensagem legível"}`. Respostas de conta nunca são cacheadas. Quando o banco de contas não estiver configurado
ou a conexão for somente-leitura, as rotas de conta respondem HTTP 503 com `{"error":"As contas não estão configuradas neste servidor."}`.

## 5. Administração — opcional
Código e CSS originais incluídos; prévia fica no login.
- GET /api/session → {"actor":null} ou identificador string.
- POST /api/session recebe username e password; sucesso HTTP 2xx; erro JSON com error.
- DELETE /api/session encerra sessão.
- GET /api/admin retorna arrays retailers, store_contexts, products, offers, review_items, flyers, collection_runs e audit_log.
- POST /api/admin recebe {"action":"...","data":{...}}.
Os formulários e chamadas act em components/admin.tsx definem campos e ações. O painel usa registros dinâmicos; alinhar contrato administrativo ao modelo do backend.
As rotas de sessão incluídas são respostas demonstrativas: não autenticam e não são a conta do usuário
(`/api/session` é o login administrativo, ainda sem backend). Não há rota /api/admin. Implementar autorização
administrativa antes de habilitar telas internas.

## 6. Sequência sugerida
1. Executar /demo e conferir referências.
2. Copiar componentes, CSS, ícone e utilitários para o projeto de destino.
3. Mapear modelos do backend para Data, usando fixtures como exemplo.
4. Ligar GET /api/public e remover demo da página principal.
5. Integrar endereço, mídia e, se necessário, administração.
6. Conferir mobile/desktop, estados de erro/vazio, condições, lista, links e encartes.
7. Avaliar os recursos PWA antes de ativá-los no domínio final; sw.js é o original.