# Homepage, endereço e proximidade — 20/09/2026

O filtro **Perto de você → Definir local** aceita endereço/bairro em Fortaleza ou localização do aparelho, solicitada somente após tocar em **Usar minha localização**. O usuário escolhe um resultado e um raio de 2, 5, 10 ou 20 km. O filtro pode ser alterado/removido e permanece durante a sessão, inclusive após recarregar. As sessões de dados reais e demonstração usam chaves separadas.

**Prévia local:** http://192.168.0.144:3000/ no mesmo Wi-Fi/rede do computador. Desenvolvimento iniciado com `npm run dev -- --hostname 0.0.0.0 --port 3000`. O computador precisa permanecer ligado e o servidor em execução. O IP pode mudar conforme o roteador. Nenhum deploy público foi feito.

## Experiência

- A abertura traz **Ofertas do dia** e destaca a diferença verificável para o próximo preço do mesmo produto/embalagem em outra rede. Não afirma ser o menor preço de toda Fortaleza. Sem dois preços comuns atuais, não exibe selo de economia. Ao incluir preços de clube, o selo só aparece se o par de ofertas exibido ainda for exatamente o par usado no cálculo.
- **Comparar N preços** mostra também o outro valor no cartão e abre todas as opções do produto. Condições, origem, localização e compartilhamento permanecem disponíveis na comparação.
- O raio filtra cartões, comparação, destaque e estimativa da lista. Opções fora dele podem ser vistas pelo botão explícito **Ver preços em todas as lojas**. Um link compartilhado abre sua oferta sem herdar um raio que a esconderia e não contém a posição do usuário.
- Distância em linha reta até a unidade, não rota, prazo ou área de entrega. Preços online continuam identificados; proximidade não confirma o mesmo valor no balcão ou estoque.
- Unidade sem coordenadas não é considerada próxima. Ausência de cobertura explica o raio e permite remover o filtro. O piloto continua com apenas duas unidades reais.
- Cartões de texto compactos evitam gastar a primeira dobra com espaços de imagem vazios. Busca mobile permanece fixa acima da navegação. Categorias mobile ficam em **Buscar → Filtros**; no desktop continuam acessíveis na busca.

## GPS e endereço manual

O GPS exige contexto seguro: HTTPS ou localhost no próprio computador. O endereço HTTP da rede local **não libera GPS no celular**. O botão explica essa limitação e mantém o endereço manual disponível; não há contorno da permissão nem publicação/túnel público. Permissão negada, ausência de suporte, timeout e precisão pior que 2 km também têm alternativa manual. Testes de GPS usaram coordenadas simuladas, nunca a posição real do usuário.

As coordenadas do aparelho não são enviadas pela aplicação ao servidor nem a serviços de geocodificação; ficam em `sessionStorage`. Não há geocodificação reversa. O endereço manual digitado é enviado ao serviço Photon somente ao submeter a busca, com aviso no diálogo; não há autocomplete ou consulta a cada tecla. Respostas são limitadas a Fortaleza e exigem escolha explícita do usuário.

`POST /api/location`: mesma origem (inclui o acesso pelo IP local), no-store, entrada de 3–120 caracteres, leitura do corpo limitada a 4096 bytes/5 segundos, até 10 consultas/minuto por instância no padrão local, uma chamada externa por segundo, timeout de 10 segundos e resposta externa até 256 KiB. Cache em memória de até 100 consultas por 30 minutos. Sem redirects, tentativa em fonte alternativa ou repetição automática. Os endereços não são gravados no banco, em relatórios ou em URLs do cliente.

Serviço público Photon usado apenas moderadamente no piloto, conforme sua documentação; disponibilidade não garantida. Produção/escala exige provedor adequado ou instalação própria. A API pública Nominatim não é usada. Fontes: [Photon](https://github.com/komoot/photon/blob/master/README.md), [API Photon](https://github.com/komoot/photon/blob/master/docs/api-v1.md), [política Nominatim](https://operations.osmfoundation.org/policies/nominatim/), [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API).

## Coordenadas verificadas

Migração `005_store_coordinates.sql`: latitude, longitude e origem opcional no contexto da unidade, mantendo os adaptadores SQLite/PostgreSQL. A inicialização idempotente do piloto preenche somente contexto verificado cujo endereço ainda coincide com o revisado e cujos campos geográficos estejam vazios. Não sobrescreve edição posterior.

| Unidade | Latitude, longitude | Correspondência conferida |
| --- | --- | --- |
| Supribem, Av. Aguanambi, 880 | -3.7442616, -38.5258994 | [OSM node 10815351521](https://www.openstreetmap.org/node/10815351521); rua/número coincidem com a [página oficial](https://www.supermercadosupribem.com.br/matriz/nossas-lojas) |
| Atacadão do Alimento, Rua Coronel Alexandrino, 405 | -3.7638083, -38.5541144 | [OSM way 1165271869](https://www.openstreetmap.org/way/1165271869); rua/número coincidem com a [página oficial](https://atacadaodoalimento.com.br/) |

O resultado de nome na Rua Almirante Rubim foi descartado por corresponder a outro endereço. O bairro do Supribem foi mantido conforme a fonte oficial (José Bonifácio), embora o mapa classifique o ponto como Fátima. Evidências locais: `data/location-audit/supribem.json` e `atacadao-address.json`. Coordenadas de lojas fictícias estão somente em `lib/demo.ts`, identificadas como fictícias no diálogo.

## Validação

- 61 testes de domínio/API/coletores, incluindo Haversine, coordenadas ausentes/inválidas, raio, sessão, comparações equivalentes, geocoder com fixtures, cache, limites, rejeição de outra cidade, origem LAN e cancelamento da leitura antes de consumir corpo excessivo. [Saída](evidence/nearby-home-unit.txt).
- 64 cenários E2E em Chromium desktop e WebKit mobile: endereço manual, escolha de resultado, GPS simulado e solicitado apenas por gesto, negação/precisão/HTTP, alteração do raio, lista e comparação consistentes, persistência/separação, falta de cobertura, erro externo, link compartilhado e preço condicionado. A suíte anterior de busca, contatos, lista, encartes e compartilhamento também passou. [Saída](evidence/nearby-home-e2e.txt).
- Primeiro produto inteiro acima da busca fixa em 390×664 e 320×640, inclusive no demo. Inspeção visual adicional com os preços reais a 320 px e no desktop.
- Consulta externa real, pela interface, para Rua Coronel Alexandrino 405: retorno exato, raio de 2 km mostrou somente a oferta do Atacadão do Alimento. Consulta real de **Montese** pelo endpoint LAN também retornou o bairro e opções de referência.
- GPS real em celular físico/HTTPS, instalação PWA e operação em PostgreSQL não foram validados nesta etapa. Nenhuma mensagem, compra ou chamada foi feita.

O build de verificação usa `MED_E2E=true` apenas para gerar `.next-e2e`, preservando a prévia de desenvolvimento em `.next`; não altera a aplicação nem publica o build. Evidência: [build](evidence/nearby-home-build.txt).
