# Verificação desta entrega — 21/09/2026
- Instalação limpa com npm ci: aprovada (cache local alternativo; o cache global deste computador falhou).
- npm run typecheck: aprovado.
- npm run build: aprovado; Next.js 16.3.5, build webpack.
- Build servido localmente e navegado em Chromium headless, larguras 320, 390 e 1280px.
- Em cada largura: Hoje, abrir leitor de encarte, buscar café, abrir comparação, adicionar à lista e recuperar lista após recarregar: aprovados.
- Nenhum erro JavaScript não tratado nos fluxos verificados.
- Sem transbordamento horizontal da página inicial nas três larguras.
- Raiz, login, manifesto e duas páginas SVG de encarte responderam HTTP 200.
- Endereço respondeu 501 e sessão retornou actor null, conforme limites de demonstração.
- Doze capturas novas e resultados estruturados em referencias/preview.
- Inspeção visual direta das capturas Hoje em 390px e comparação em 1280px.
- Componentes originais e CSS comparados por SHA-256 com a origem.
- ZIP inspecionado após criação; arquivos inventariados e hashes conferidos.

Limites: não se executou a suíte completa do projeto original, nem testes em aparelho físico, backend de destino, login real, GPS real, compartilhamento entre aplicativos ou instalação PWA. As capturas em referencias/historicas e os relatórios citados nos textos originais são evidências anteriores, não testes desta entrega.
O aviso original "Voltar aos dados reais" aponta para a raiz, que também é demonstrativa neste pacote. Não há dados reais no pacote.