# Planos executáveis — UI e motion

Cada plano segue o modelo `improve-animations/PLAN-TEMPLATE.md` (emilkowalski/skills): problema com o código
atual citado, alvo com todos os valores, convenções do repositório, passos, limites e verificação com
"feel check". Um executor sem contexto desta conversa deve conseguir aplicar cada plano sozinho. O plano
mestre com o raciocínio está em [../PLANO-UI-MOTION.md](../PLANO-UI-MOTION.md).

Commit de referência de todos os planos: `12e46d0` (`main`) + as alterações locais, ainda não commitadas,
da branch `ux/auditoria-experiencia` (auditoria de UX de 27/09/2026). Se o código encontrado não bater com
o trecho citado, pare e relate; não improvise.

| # | Plano | Severidade | Categoria | Fase | Status |
|---|---|---|---|---|---|
| 000 | [Tokens, fundação e canvas gelo](000-tokens-fundacao-e-canvas.md) | HIGH | Cohesion & tokens | 0 | DONE 27/09 (`tokens/`, `app/tokens.css`, `npm run tokens:check` no `prebuild`; 0 literais em `globals.css`) |
| 001 | [Tipografia: Archivo e escala](001-tipografia-archivo.md) | HIGH | Cohesion & tokens | 0 | DONE 27/09 (Archivo Variable auto-hospedada; escala de nove passos; preço `wdth 90` tabular; sem preload com hash, ver nota) |
| 002 | [Tokens de motion, reduced motion e pressionar](002-motion-tokens-reduced-motion-press.md) | HIGH | Accessibility · Easing & duration | 0 | DONE 27/09 (tokens em `tokens.css`; reduced motion mantém fades; `:active` com escala em todo pressionável; hover com `pointer: fine`) |
| 003 | [Diálogos: entrada e saída](003-dialogos-entrada-e-saida.md) | HIGH | Physicality & origin | 2 | DONE 28/09 (`components/ui/use-dialog.ts`; saída via `data-closing`; `@starting-style` com a especificidade da regra aberta) |
| 004 | [Skeletons, fotos e busca sem salto](004-skeletons-fotos-e-busca.md) | HIGH | Missed opportunities | 2 | DONE 28/09 (`components/ui/skeleton.tsx`; véu `.results[data-busy]`; fotos com `data-loaded`) |
| 005 | [Toast com Sonner e Desfazer](005-toast-sonner-desfazer.md) | MEDIUM | Interruptibility | 2 | DONE 28/09 (`lib/notify.tsx`; Desfazer no toast e no aviso da lista) |
| 006 | [View Transitions: herói do produto e abas](006-view-transitions-heroi-e-abas.md) | MEDIUM | Missed opportunities | 3 | DONE 28/09 (`lib/view-transition.ts`; pílula e marcador com `use-indicator.ts`; faixa com entrada única e máscara) |
| 007 | [Select, tooltip e checkbox desenhados](007-select-tooltip-checkbox.md) | MEDIUM | Cohesion & tokens | 1 | DONE 28/09 (Base UI em `select.tsx` e `tooltip.tsx`; `checkbox.tsx` nativo desenhado; `segmented.tsx`) |
| 008 | [Bottom sheet no mobile](008-bottom-sheet-mobile.md) | MEDIUM | Physicality & origin | 4 | DONE 28/09 (`components/ui/use-sheet-drag.ts` com mola própria; `motion` medido em 19 kB gzip e removido; três diálogos viram sheet abaixo de 760 px) |
| 009 | [Botões, campos e chips: grade de estados e vitrine](009-botoes-campos-chips-vitrine.md) | HIGH | Cohesion & tokens | 1 | DONE 28/09 (`components/ui/{button,field,chip}.tsx`; vitrine em `/demo?vitrine=1`) |

Notas da fase 0: a migração de `globals.css` foi feita por script (literais → tokens semânticos, `font-size`
→ escala, `border-radius` → escala, `:root` legado → aliases gerados) e uma camada final "Phase 0" no próprio
arquivo redefine corpo, títulos, preço, overlines e superfícies. O preload do woff2 foi deixado de fora: o Vite
dá hash ao nome do arquivo e o fallback com métricas do capsize já evita o salto de layout. O eixo `tnum` foi
confirmado no navegador (`font-variant-numeric: tabular-nums` ativo).

Notas das fases 1–4 (28/09): cada plano acrescentou uma camada comentada ao fim de `globals.css` ("Phase 1
(plan 009)", …) e retirou por script as regras que substituía; os aliases legados (`--green`, `--muted`…) foram
trocados pelo nome semântico conforme a propriedade (texto → `text-*`, fundo → `interactive-*-fill-*`, borda →
`border-*`) e removidos de `tokens.json`; `npm run tokens:check` passou a reprovar qualquer `var(--x)` que não
seja token. Desvios do texto dos planos estão na linha de status de cada um e em
[../PLANO-UI-MOTION.md](../PLANO-UI-MOTION.md), seção 12. Resultados: [../VALIDACAO.md](../VALIDACAO.md).

## Ordem recomendada

1. **000 → 001 → 002** (fundação; 001 pode esperar a decisão da fonte sem bloquear 002).
2. **009 → 007** (vocabulário de componentes; 007 introduz Base UI).
3. **003 → 004 → 005** (estados em movimento).
4. **006** (navegação) e depois **008** (mobile; introduz `motion`).

Dependências: 002 depende de 000 (tokens em `tokens.css`); 003, 004, 006 e 008 dependem de 002 (curvas e
durações); 009 depende de 000 e 001; 005 e 007 dependem só de 000. Tudo passa por `npm run typecheck`,
`npm test`, `npm run build` e `node tokens/check.mjs` antes de ser dado como concluído.
