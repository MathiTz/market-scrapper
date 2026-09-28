<!-- Portado do PRODUCT.md do MVP anterior (mercado-em-dia/, 20/09/2026) e atualizado em 27/09/2026 com a direção dada pelo proprietário para a evolução visual. As seções "Brand Personality", "Anti-references" e o último princípio ainda dependem de confirmação. -->

# Product

## Register

product

## Users

Pessoas de Fortaleza que consultam preços de supermercados antes de sair de casa, principalmente pelo celular, muitas vezes com pressa e no meio de outra tarefa (montando a lista da semana, conferindo se vale ir a outra loja). Também usam no desktop para comparar com calma quando a compra é grande.

Contexto físico: tela do celular em casa ou na rua, luz ambiente variada, uma mão livre; no desktop, uma aba aberta ao lado do encarte ou do site do mercado.

## Product Purpose

Consultor de preços: encontrar ofertas monitoradas na região, comparar o mesmo produto entre redes (com embalagem, condição e origem explícitas), consultar encartes e planejar quantidades numa lista local. Sucesso é a pessoa decidir onde comprar e o que levar em menos de um minuto, sem ser induzida ao erro por um preço que não se aplica ao seu caso.

A aplicação não vende, não reserva, não entrega e não exige cadastro. Não há checkout.

## Brand Personality

Clara, prática e transparente. Três objetos físicos que carregam a voz: a etiqueta de preço da gôndola (o número manda), o encarte impresso de supermercado (preço grande, condição pequena mas legível) e o recibo (tabular, honesto, sem enfeite).

O visual deve sair do estado de wireframe: tipografia com identidade própria, controles desenhados (não os nativos do navegador), estados de interação em tudo que é clicável, movimento que explica abertura, fechamento e carregamento. Verde continua sendo a cor da marca, mas como acento e ação, não como fundo de página.

## Anti-references

- Aparência e linguagem de checkout, carrinho de compras ou promessa de disponibilidade.
- Exemplos fictícios apresentados como ofertas reais.
- Fundo de página verde-claro ou qualquer superfície tingida de verde; o verde fica nos botões, seleções e marca.
- Cara de protótipo: `select`, `checkbox`, tooltips e barras de rolagem no estilo padrão do navegador; fonte de sistema; cortes secos ao abrir e fechar.
- Landing page de SaaS: eyebrows em caixa alta com tracking em toda seção, cartões idênticos em grade, número gigante com rótulo pequeno, gradiente em texto, vidro fosco decorativo.
- Motion decorativa: bounce, elástico, coreografia no carregamento da página, parallax, animação em ação de teclado.

## Design Principles

- Priorizar a informação útil para decidir onde consultar ou visitar: preço, embalagem, condição, rede, quando foi visto.
- No mobile, manter a busca junto à navegação inferior e o primeiro produto visível antes de rolar.
- Identificar no cartão a rede e o alcance do preço (site da rede, não uma filial); só apontar filial quando a pessoa definiu a própria referência.
- Preservar origem, condições e validade dos preços; nenhuma afirmação sem escopo ("menor preço" só com dois ou mais preços comparáveis).
- Separar integralmente a demonstração dos dados reais; informar lacunas de cadastro.
- O movimento serve ao estado: abrir, fechar, carregar, confirmar. Cada animação tem propósito nomeado, dura menos de 300 ms na UI e tem alternativa para quem prefere menos movimento.
- Uma só linguagem de componentes em todas as telas: mesmo botão, mesmo campo, mesmo cartão, mesma escala de espaço e de tipo, sem valores avulsos.

## Accessibility & Inclusion

WCAG 2.2 AA como piso: contraste ≥ 4,5:1 em texto e ≥ 3:1 em foco e ícones informativos; navegação por teclado com foco visível e devolvido ao fechar diálogos; alvos de toque ≥ 44 px; reflow até 320 px sem rolagem horizontal; `prefers-reduced-motion` respeitado com movimento reduzido, não zerado; hover só com ponteiro real; nenhuma informação comercial só em tooltip ou só em cor.
