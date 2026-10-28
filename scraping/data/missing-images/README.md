# Imagens faltantes — lote de 29 produtos

Resolvido em **2026-10-28**. 25 de 29 produtos ganharam imagem; 4 nao existem com foto no Cosmos.

## Como foi feito (ordem de custo)

1. **Open Food Facts por GTIN** (o pipeline atual, `services/image_enrichment.py`): dos 9 GTINs,
   só `7898692301290` existia e **sem foto**. Cobertura praticamente nula para estes itens.
2. **CDN do Cosmos pelo código de barras** — padrao `https://cdn-cosmos.bluesoft.com.br/products/{gtin}`
   (GTIN-13, sem o zero a esquerda). Exato, sem busca. Resolveu 4 dos 9.
3. **Busca do Cosmos por nome** (`/pesquisar?q=`), escolhendo marca + produto + peso.
   Foi assim que sairam os 21 restantes.

> Atencao: o CDN responde **HTTP 200 com HTML** quando o produto existe mas nao tem foto.
> Validar os magic bytes (`\x89PNG`, `\xff\xd8\xff`, `GIF8`, `RIFF`), nunca só o status.

## Status

- **OK** (10) — marca e produto conferem; GTIN igual ou variante equivalente.
- **REVIEW** (15) — imagem plausível mas de outro GTIN/peso/sabor, ou placeholder genérico. Conferir antes de aplicar.
- **NONE** (4) — nada utilizavel no Cosmos.

## Arquivos

| Arquivo | Conteudo |
|---|---|
| `final_lookup.csv` | 29 linhas: status, GTIN usado, URL do CDN, arquivo local, observacao |
| `final_lookup.json` | mesma coisa em JSON |
| `images/NN_GTIN.ext` | 25 imagens baixadas (PNG/JPEG/GIF conforme o original) |

Colunas: `num,name,gtin_input,status,matched_name,matched_gtin,note,image_url,file,bytes,dims`

## Sem imagem (4)

| # | Produto | Por quê |
|---|---|---|
| 3 | Atum sólido Gomes da Costa | O produto existe no Cosmos, mas **nenhum** atum Gomes da Costa cadastrado tem foto |
| 5 | Bebida Vegetal Possible Aveia 1L | GTIN `7898692303188` cadastrado, sem foto. Só a variante morango (`7898692301917`) tem imagem |
| 6 | Bebida Vegetal Possible Aveia Amêndoas 1L | idem, sem foto |
| 21 | Lava-Roupas Qualitá Tripla Ação 3L | marca de varejo sem foto; só Ariel/Brilux 3L têm imagem |

## Cuidados por item (REVIEW)

- **#1** GIF 41x138, marca ilegível — praticamente inutilizável, apesar de ser espaguete.
- **#24** a foto é **Pullman Artesano**, nao Plusvita (mesmo grupo), 84x208 e desfocada.
- **#11** 3 Corações liofilizado 40g refil, mas **nao** é o Gourmet Descafeinado.
- **#8** pack de 12 YoPro coco; **#26** Aconchego 2L em vez de 6L; **#20** zero açúcar 200g em vez de 250g.
- **#18** Mãe Terra 800g sabor **cacau**.
- **#22** coxinha Sadia genérica (La Maison nao tem foto).
- **#15** Ariel Expert 1,2L — marca inferida do OCR "EXPERI".
- **#9/#16** cortes equivalentes (chorizo Wessel, filé mignon Swift 1kg).
- **#12** chuchu genérico 500g para item de peso variável.
- **#27/#28/#29/#10** marca provável (Qualy, Heinz, NutriLevis, Quaker).
