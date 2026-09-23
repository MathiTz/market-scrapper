# Mercado em Dia — entrega da interface
Preparado em 21/09/2026 a partir da cópia local fornecida pelo proprietário.

## Comece aqui
Este pacote entrega o código visual existente em React + Vite + TypeScript (dados com TanStack React Query), CSS e componentes, acompanhado de demonstração sem banco de dados. O desenvolvedor deve adaptar o contrato de dados ao backend dele.

Requisito: Node.js 24 ou superior e npm. Na pasta deste README, execute:

    npm ci
    npm run dev

Abra http://127.0.0.1:3000/demo. A raiz / também abre a demonstração. Não precisa configurar .env, banco ou senha. Se houver problema com o cache global do npm, use: npm ci --cache ../npm-cache

Para validar e executar o build:

    npm run typecheck
    npm run build
    npm run preview

## Conteúdo
- components/: componentes originais, incluindo painel administrativo.
- app/globals.css: estilos completos, cores, tipografia e responsividade originais.
- index.html, app/main.tsx, public/: entrada da aplicação, rotas (/, /demo, /admin), ícone e recursos PWA.
- lib/: tipos e funções utilizadas pela interface; fixtures fictícias.
- INTEGRACAO.md: contrato de dados e roteiro para conectar o backend.
- VISUAL.md: mapa de telas, componentes e critérios de conferência.
- ALTERACOES.md: diferenças entre esta entrega e o projeto original.
- referencias/historicas/: capturas e textos encontrados na origem; não são novas validações desta entrega.
- referencias/preview/: capturas novas da demonstração separada.
- VALIDACAO.md: verificações realizadas nesta entrega.
- MANIFESTO-SHA256.csv: inventário, hashes e indicação dos arquivos idênticos à origem.

## O que funciona sem backend
Hoje, busca local por nome, comparação, filtros locais existentes, encartes fictícios com leitor, lista e quantidades no navegador, modal de localização e compartilhamento conforme suporte do navegador. As telas públicas usam estado interno; não há URL separada para cada aba.

A demonstração usa três produtos e duas redes fictícias. Há produto com preço antigo para representar esse estado. As fotos ficam no estado "Sem foto" porque as fixtures originais não possuem imagens. As capturas históricas mostram cartões com fotos; o backend deve fornecer image_url para esse estado.

## Limites explícitos
- Busca textual de endereço retorna mensagem de integração pendente. GPS depende de permissão e contexto seguro, como localhost ou HTTPS.
- /admin exibe o login original; autenticação e operações administrativas dependem do backend. O código das telas internas está em components/admin.tsx.
- Preços, estoque, endereços e contatos fictícios não representam ofertas reais.
- Arquivos PWA incluídos, mas service worker não é registrado no modo demo.
- Links example.com são marcadores das fixtures, não integrações com supermercados.
- Banco, workers, rotas reais de API, credenciais, .env, Git e node_modules não fazem parte do ZIP.
- Não houve deploy nem integração automática com o backend do destinatário.

## Como receber no projeto do desenvolvedor
Com React/Vite, pode reaproveitar componentes e CSS, adaptando as APIs conforme INTEGRACAO.md. Com outra tecnologia, deve usar a prévia e as referências para portar a interface. O código executável é a entrega principal porque preserva componentes, estados e comportamentos.