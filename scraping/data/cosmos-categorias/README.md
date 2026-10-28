# Cosmos — árvore de categorias (4 ramos)

Extração pontual do site publico `cosmos.bluesoft.com.br`, feita em **2026-10-28**.
Lista **separada** de proposito: nada aqui esta ligado ao banco, models ou seed do projeto.
Aponte o ETL para esta pasta quando quiser consumir.

| Ramo (`root`) | Nós | Profundidade máx. | Folhas |
|---|---:|---:|---:|
| Alimentos e Bebidas | 278 | 5 | 214 |
| Eletro | 43 | 4 | 32 |
| Higiene e Beleza | 78 | 4 | 55 |
| Limpeza | 29 | 2 | 23 |
| **Total** | **428** | 5 | **324** |

Crawl BFS completo, 0 falhas, sem produtos individuais. Cada ramo foi extraido do seu
proprio hub: `/categorias/alimentos-e-bebidas`, `/categorias/eletro`,
`/categorias/higiene-e-beleza`, `/categorias/limpeza`. `depth` e relativo ao ramo.

## Arquivos

| Arquivo | Linhas | Conteudo |
|---|---|---|
| `categorias.csv` | 428 | lista plana, uma linha por categoria |
| `categorias.json` | 428 | mesma lista em JSON |
| `categorias_tree.txt` | 428 | arvore identada, 4 ramos, para leitura humana |
| `categorias_tree.json` | 428 | mapa `href -> {name, slug, path[], children[]}` |
| `live_only.csv` | 205 | **so Alimentos e Bebidas**: existe no site, nao na lista de referencia |
| `mapping.csv` | 168 | **so Alimentos e Bebidas**: lista de referencia -> categoria viva |

## Colunas de `categorias.csv`

```
root,path,name,slug,parent_slug,depth,children_count,is_leaf,url
```

- `root` — ramo de topo: `Alimentos e Bebidas` · `Eletro` · `Higiene e Beleza` · `Limpeza`
- `path` — caminho completo separado por ` > `, comecando no `root`
- `slug` — ultimo segmento da URL da categoria
- `parent_slug` — vazio apenas no nó do `root`
- `depth` — 0 = o proprio ramo
- `children_count` — filhos conhecidos dentro da extracao
- `is_leaf` — `1` quando nao ha filhos
- `url` — URL absoluta

> Schema mudou nesta versao: `root` foi adicionada como **primeira** coluna.
> Quem lia por posicao precisa ajustar; quem le por cabecalho nao.

## Avisos para o ETL

1. **Nao use `slug` como chave unica.** Cinco categorias carregam UUID no slug:
   - `cervejas-74f08a6d-d6a6-4f1d-a60c-c07059945db0`
   - `manteiga-c574feb6-1757-410a-a65c-9fcd7ddc0ec0`
   - `mascaras-faciais-f40e10d1-62f1-4d56-aaf6-e4c13d5fb1af`
   - `acetona-69cf1266-33bf-40c5-9c14-af13541b02e7`
   - `protetor-solar-724f487c-863d-484c-a3f6-4bdf08e0bf2d`

   `Cervejas Tradicionais` também responde por `/categorias/cervejas`.
2. **Slug nao bate com o nome** em varios casos: `Doces`->`/balas`, `Cereais`->`/aveia-e-mingau`,
   `Molho de tomate`->`/atomatados`, `Chiclete e Goma de Mascar`->`/chiq`, `Cachaça Tradicional`->`/tradicional`,
   `Maquiagem para Boca e Lábios`->`/batom-e-gloss`, `Lava-louças`->`/detergente-para-loucas`.
3. **Erros de grafia na origem**: `Maça`, `Batata Doce`->`bata-doce`, `Xarópes`, `Cerveja sem Alcóol`,
   `Açucar`, `Oregano`, `Castanha de Cajú`, `Café em Capsulas`, `pasta-de-amendoim-ou-novez`,
   `Higiene Bucal`->`higiene-buscal`, `Cuidados com a unhas`, `Cuidados com mãos e pés`->`cuidados-com-a-maos`.
4. **Ingles no meio do PT**: `Jerky & Dried Meats`, `Café - Coffee Creamers`, `Wifi & Roteadores`,
   `Amazon Echo, Alexa, Smart Devices`, `Perecíveis, resfriados e congelados` (minuscula no meio).
5. `Ovos` e **folha** no site (nao existe Ovos de Galinha/Caipiras/Brancos/Vermelhos).
6. **`Eletro` e majoritariamente eletronicos**, nao eletrodomesticos: `Eletrônicos` (12 filhos) concentra
   celulares, computadores, audio, TVs, tablets. Eletrodomesticos de linha branca praticamente nao existem
   (so `Aspiradores de Pó` e `Máquina de Café`).
7. A arvore viva de Alimentos tem uma **camada intermediaria a menos** que a lista de referencia em
   `Mercearia Alto Giro`, `Mercearia Doce`, `Matinais` e `Perecíveis Lácteos`.
