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
Lista não sincroniza entre dispositivos; isso exige implementação adicional.

## 4. Administração — opcional
Código e CSS originais incluídos; prévia fica no login.
- GET /api/session → {"actor":null} ou identificador string.
- POST /api/session recebe username e password; sucesso HTTP 2xx; erro JSON com error.
- DELETE /api/session encerra sessão.
- GET /api/admin retorna arrays retailers, store_contexts, products, offers, review_items, flyers, collection_runs e audit_log.
- POST /api/admin recebe {"action":"...","data":{...}}.
Os formulários e chamadas act em components/admin.tsx definem campos e ações. O painel usa registros dinâmicos; alinhar contrato administrativo ao modelo do backend.
As rotas de sessão incluídas são respostas demonstrativas: não autenticam. Não há rota /api/admin. Implementar autorização e sessão no backend antes de habilitar telas internas.

## 5. Sequência sugerida
1. Executar /demo e conferir referências.
2. Copiar componentes, CSS, ícone e utilitários para o projeto de destino.
3. Mapear modelos do backend para Data, usando fixtures como exemplo.
4. Ligar GET /api/public e remover demo da página principal.
5. Integrar endereço, mídia e, se necessário, administração.
6. Conferir mobile/desktop, estados de erro/vazio, condições, lista, links e encartes.
7. Avaliar os recursos PWA antes de ativá-los no domínio final; sw.js é o original.