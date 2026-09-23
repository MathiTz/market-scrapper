# Cards compactos de produtos — 20/09/2026

A homepage apresenta ofertas em uma faixa horizontal com encaixe ao deslizar, indicação de continuidade e setas no desktop. A busca conserva sua grade de resultados. Ambos usam o mesmo card: foto pequena, produto e marca no título, embalagem, preço, loja, endereço completo, distância, localização, compartilhamento e inclusão na lista. A diferença para outra loja fica na linha de comparação.

O aviso “Preço online. Na loja, o valor pode variar.” aparece abaixo das ações, como texto discreto, sem tag. Apenas a nota genérica de preço online do piloto deixa de ser repetida como condição. Regras de clube, cupom, pagamento, quantidade mínima e restrições específicas continuam visíveis.

## Localização

O card usa o endereço e as coordenadas da mesma oferta que determina seu preço. O endereço permite quebra de linha, sem reticências. Sem cadastro, informa a ausência. A distância é aproximada, em linha reta: “de você” para GPS autorizado pelo usuário e “da sua referência” para endereço manual. Sem referência escolhida, orienta definir o local; não inventa uma distância. A seleção continua disponível em **Perto de você → Definir local**.

No celular acessando o endereço HTTP do Wi-Fi, use a opção manual. O requisito de HTTPS para GPS permanece. Coordenadas e separação real/demo seguem o fluxo de localização existente.

## Fotos oficiais

As seis imagens vêm do `og:image` e da imagem principal identificados nas páginas oficiais de produto do Supribem já armazenadas pelo piloto em 20/09/2026. São exibidas diretamente de `phygital-files.mercafacil.com`; não foram geradas, baixadas para publicação nem confundidas com imagens de produtos relacionados. A associação em `lib/product-media.ts` exige ID e assinatura do produto revisado, incluindo marca, variante e embalagem.

A imagem identifica o produto, e pode acompanhar o preço de outra rede quando se trata exatamente do mesmo produto e embalagem. A API inclui `image_source_url` para registrar sua origem. Novos produtos não recebem fotos por aproximação; sem imagem revisada ou quando ela falha, o card mantém “Sem foto”. Os dados fictícios de `/demo` não usam essas fotos reais.

Não houve migração, alteração de preços, nova fonte de coleta, mudança no agendamento ou deploy público nesta atualização.

## Verificação

Regras de associação das fotos e preservação de condições têm testes dedicados. A suíte de navegador verifica foto/falha de imagem, marca no título, endereço sem corte, posição e estilo do aviso, distância manual/GPS, rolagem horizontal, avanço no desktop, foco por teclado, primeira dobra e busca fixa. Resultados da execução desta atualização estão em [relatório de testes](test-report.md).

As seis fotos foram carregadas na prévia local e conferidas pelo navegador. Testes de layout usam Chromium desktop e WebKit com viewport mobile; a confirmação no iPhone físico do usuário continua pendente.
