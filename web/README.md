# Mercado em Dia — entrega da interface
> **Estado atual (27/09/2026):** a interface é Vite + React + TypeScript com TanStack React Query (veja
> [AGENTS.md](AGENTS.md)); as seções abaixo descrevem o pacote de handoff de 21/09 e citam Next.js, que não
> é mais usado. Auditoria de UX, jornada, estados e validação atuais: [AUDITORIA-UX.md](docs/AUDITORIA-UX.md),
> [ESTADOS-UX.md](docs/ESTADOS-UX.md) e [VALIDACAO.md](docs/VALIDACAO.md).

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
- components/: componentes originais, incluindo painel administrativo; components/ui/: primitivos (botão,
  campo, chip, select, tooltip, checkbox, segmentado, skeleton) e hooks de diálogo/sheet; components/vitrine.tsx:
  vitrine de estados em /demo?vitrine=1.
- tokens/: fonte dos tokens de design (tokens.json → app/tokens.css por `npm run tokens`) e os verificadores
  (`npm run tokens:check`).
- app/globals.css: estilos completos, cores, tipografia e responsividade originais.
- index.html, app/main.tsx, public/: entrada da aplicação, rotas (/, /demo, /admin), ícone e recursos PWA.
- lib/: tipos e funções utilizadas pela interface; fixtures fictícias.
- docs/: documentação de processo (auditoria de UX, plano de design/motion, produto, validação) - veja
  docs/AUDITORIA-UX.md, docs/VALIDACAO.md e docs/plans/.
- INTEGRACAO.md: contrato de dados e roteiro para conectar o backend.
- ALTERACOES.md: diferenças entre esta entrega e o projeto original.
- referencias/historicas/: capturas e textos encontrados na origem; não são novas validações desta entrega.
- referencias/preview/: capturas novas da demonstração separada.
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