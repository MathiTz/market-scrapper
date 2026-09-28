# Capturas da auditoria de UX — 27/09/2026

> As imagens, os relatórios JSON e os roteiros de captura descritos abaixo foram usados na preparação desta
> auditoria mas não foram mantidos no repositório (evitar versionar ~10 MB de binários e scripts de uso
> pontual). Este arquivo registra o método para referência; os resultados estão resumidos em
> [AUDITORIA-UX.md](AUDITORIA-UX.md) e [VALIDACAO.md](VALIDACAO.md).

- "Antes": código de `main` @ `12e46d0`. "Depois": branch `ux/auditoria-experiencia`.
- Mesmos dados nos dois lados: cópia congelada do snapshot público de produção (`GET /api/public` em
  27/09/2026, `generated_at` 12:04 de Fortaleza), servida por um servidor local de teste, que também simula
  503, demora sem resposta e snapshot vazio. Nenhuma coleta, publicação ou deploy.
- Relógio fixo em 27/09/2026 18:00 (America/Fortaleza), Chromium headless (Playwright 1.63), escala 1x,
  movimento reduzido (o leitor de encartes fica pausado).
- Nome dos arquivos: `<largura>-<cena>.png`. Capturas de página inteira escondiam o dock fixo do mobile
  (busca + navegação), que apareceria no meio da imagem; as de viewport o mostravam.
- Fotos de produtos vêm dos sites das redes e podiam aparecer em branco quando não carregavam a tempo.
- Fases capturadas: o estado antes da auditoria, depois da fase 0 do [PLANO-UI-MOTION.md](PLANO-UI-MOTION.md)
  (tokens, canvas branco-gelo, Archivo, escala de tipo, reduced motion e pressionar), e depois dos planos
  003–009 (componentes, Base UI, diálogos, skeletons, toasts, View Transitions, bottom sheets), incluindo a
  cena `vitrine` (`/demo?vitrine=1`).
- Um roteiro à parte percorria 8 telas registrando, por tipo de controle, se algo mudava visualmente ao
  passar o ponteiro (comparação de pixels do próprio elemento).

## Como repetir

Os passos abaixo descrevem o método; os scripts em si (`capture.mjs`, `flows.mjs`, `hover-audit.mjs`,
`mock-api.mjs`, usando Playwright) precisariam ser recriados, pois não fazem parte do repositório.

1. Sirva uma cópia congelada do snapshot público (`GET /api/public`) por um servidor de teste local que
   também simule os cenários 503, demora sem resposta e snapshot vazio.
2. `npm run dev` nesta pasta `web/`, apontando para esse servidor de teste.
3. Capture as telas relevantes em Chromium headless, relógio e larguras fixos, movimento reduzido; repita
   para o commit de referência ("antes") em outra porta.
4. Rode as mesmas jornadas com asserções (fluxos) nos dois lados e compare.
