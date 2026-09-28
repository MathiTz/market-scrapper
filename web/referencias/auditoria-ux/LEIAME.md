# Capturas da auditoria de UX — 27/09/2026

- `antes/`: código de `main` @ `12e46d0`. `depois/`: branch `ux/auditoria-experiencia`.
- Mesmos dados nos dois lados: cópia congelada do snapshot público de produção (`GET /api/public` em
  27/09/2026, `generated_at` 12:04 de Fortaleza), servida por um servidor local de teste, que também simula
  503, demora sem resposta e snapshot vazio. Nenhuma coleta, publicação ou deploy.
- Relógio fixo em 27/09/2026 18:00 (America/Fortaleza), Chromium headless (Playwright 1.63), escala 1x,
  movimento reduzido (o leitor de encartes fica pausado).
- Nome dos arquivos: `<largura>-<cena>.png`. Capturas de página inteira escondem o dock fixo do mobile (busca
  + navegação), que apareceria no meio da imagem; as de viewport o mostram. `1280-comparacao-suspeita` e
  `390-comparacao-com-referencia` foram recortadas no topo.
- A terceira linha da lista (`1280-lista-completa`) difere entre os lados por efeito da correção da busca:
  "leite integral" traz leite de coco primeiro no antes e leite integral no depois.
- Fotos de produtos vêm dos sites das redes e podem aparecer em branco quando não carregaram a tempo.
- Relatórios estruturados (rolagem horizontal, erros de página, fluxos, hover): `relatorios/`.
- `fase0/`: as mesmas cenas depois da fase 0 do [PLANO-UI-MOTION.md](../../PLANO-UI-MOTION.md) (tokens, canvas
  branco-gelo, Archivo, escala de tipo, reduced motion e pressionar), 27/09/2026 à noite. Comparar com `depois/`.
- `scripts/hover-audit.mjs`: percorre 8 telas e registra, por tipo de controle, se algo muda visualmente ao
  passar o ponteiro (comparação de pixels do próprio elemento); resultados em `relatorios/hover-fase0.json` e
  `relatorios/hover-fases1-4.json`.
- `fases1-4/`: as mesmas cenas depois dos planos 003–009 (componentes, Base UI, diálogos, skeletons, toasts,
  View Transitions, bottom sheets), 28/09/2026, mais a cena `vitrine` (`/demo?vitrine=1`). Comparar com `fase0/`.

## Como repetir

Os roteiros em `scripts/` não fazem parte do `npm test` e não adicionam dependências ao projeto: exigem o
Playwright instalado à parte (`PLAYWRIGHT_MODULE` aponta para o módulo, se não estiver no caminho padrão).

1. Salve uma cópia do snapshot público como `scripts/snapshot-public.json` (não versionada: ~5 MB).
2. `node scripts/mock-api.mjs` — API de teste em `127.0.0.1:5050` (mesma porta que o proxy do `vite.config.ts`
   usa por padrão); `GET /__mode?set=real|503|500|slow|hang|empty` troca o cenário.
3. `npm run dev` nesta pasta `web/`.
4. `node scripts/capture.mjs depois` (capturas e `report.json`) e `BASE_URL=http://127.0.0.1:3000 node
   scripts/flows.mjs depois` (fluxos com asserções). Para o "antes", rode o commit de referência em outra porta
   (`npm run dev -- --port 3002`) e use `BASE_URL`.
