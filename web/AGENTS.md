# Mercado em Dia UI

A Vite + React + TypeScript single-page app. There is no Next.js here.

- Server data is fetched with TanStack React Query (`@tanstack/react-query`); keep caching and paging in query hooks rather than hand-rolled `fetch` caches.
- The UI loads one complete snapshot from `GET /api/public` and searches and filters it in the browser. Searches of 2+ characters also query `GET /api/search`
  (`lib/catalogue-search.ts`) for products beyond the snapshot; those are merged in after the snapshot's own matches
  and exist only for the session. Both backends serve that route. Shopping lists live in `localStorage`.
- In production the API is the Hono app in `../api` (Cloudflare Workers reading Postgres). `../scraping/local_api/app.py` (Flask) serves the same routes for local development. `vite.config.ts` proxies `/api` to `API_URL` (default Flask on `http://127.0.0.1:5050`; use `http://127.0.0.1:8787` for the Hono API under `wrangler dev`). Keep both backends' routes in step.
- Routes are chosen in `app/main.tsx`: `/` (real data), `/demo` (fictional data), `/demo?vitrine=1` (the
  components sheet, every primitive in every state; never on `/`), `/conta` (the shopper's account) and `/admin`.
- Design tokens live in `tokens/tokens.json` and are compiled to `app/tokens.css` by `npm run tokens` (runs
  before `dev` and `build`). Colours are authored in OKLCH and resolved to sRGB hex by `tokens/build.mjs`
  (a binary-search gamut mapping, not something to hand-compute) - never hand-edit `app/tokens.css`, it is
  generated. Styles consume only `var(--md-*)` and the motion tokens; `npm run tokens:check` (also in
  `prebuild`) fails on colour literals, off-scale radii, unknown custom properties and contrast regressions.
  See `docs/VISUAL.md`, `docs/DESIGN.md` and `docs/PLANO-UI-MOTION.md`.
- UI primitives are in `components/ui/` (Button, TextField, Chip, SelectField, Tooltip, CheckboxField,
  Segmented, skeletons, NumberFlow wrappers, `useDialog`, `useSheetDrag`, `useIndicator`). Base UI is imported
  only by `select.tsx` and `tooltip.tsx`; Sonner only by `lib/notify.tsx`; the sheet's spring in `use-sheet-drag.ts` is hand-written (no `motion`).
  Dialogs stay native `<dialog>` elements opened through `useDialog`.
- The shopping list's "Conferir com o cupom" (`components/receipt-check.tsx`) sends a receipt photo to
  `POST /api/receipt/ocr` and compares what it reads with the prices of the list's items (`lib/receipt.ts`,
  `lib/receipt-api.ts`). That route is Python (`../scraping/local_api/app.py`: OpenCV and an `OLLAMA_API_KEY`),
  which a Worker cannot host: under `npm run dev` the Flask API serves it, and in production the Worker
  (`../api/src/app.ts`) rate-limits and forwards the upload to the VPS (`../scraping/deploy/market-ocr.service`
  behind Caddy), with a shared secret, answering 501 while `OCR_URL`/`OCR_SECRET` are unset. The UI is on under
  `npm run dev` or a build with `VITE_RECEIPT_OCR=1` (set by `npm run deploy` in `../api`).
  A line is recognised by the barcode the receipt prints (`code`, from the OCR, check-digit validated), else by its name
  (`lib/product-match.ts`: abbreviations, clipped words, one misread letter, rare words weigh more, the price paid breaks
  a tie between sizes); with `scope: "catalogue"` it looks beyond the list.
  Under the result, "Onde sairia mais barato" (`components/receipt-basket.tsx`, `lib/receipt-basket.ts`) prices the same lines at each
  chain: the product bought, else a similar one (same subcategory and measure, same defining words) costed by its price per kg/L.
- Accounts (`components/account.tsx`, `components/saved-lists.tsx`, `lib/account.ts`, `lib/account-api.ts`):
  e-mail/password and Google sign-in; the account keeps copies of shopping lists and the preferred
  "Perto de você" place. Google sign-in never auto-links to an existing e-mail account (requires the
  existing sign-in method); the preferred place is saved with the browsing region and applied only while browsing that region;
  opening a saved list asks before replacing a non-empty device list, and deleting asks first. The list
  still lives in `localStorage` first - an account adds copies, it does not replace the browser's. The API
  routes are `api/src/accounts.ts` in production and `scraping/local_api/accounts.py` locally; keep both
  in step. See `docs/CONTAS.md`.
- Run `npm run dev` (port 3000), `npm run typecheck`, `npm test` and `npm run build`.

## Contribution guidelines

- Process and design documentation (audits, plans, rationale write-ups) belongs in `docs/`, not at the
  package root - only `README.md` and this file live there. Keep `docs/` markdown-only: no screenshots,
  generated reports or one-off automation scripts (`docs/.gitignore` blocks image files). If a PR needs
  visual before/after evidence, put it in the PR description on GitHub, not in the repository's history -
  a handful of screenshots is a permanent multi-megabyte cost to every future clone, forever, even once the
  PR is old news.
- Keep doc cross-references relative to the file making them (e.g. `[VALIDACAO.md](docs/VALIDACAO.md)` from
  another file already in `docs/`), so moving the whole `docs/` folder never breaks a link.
- A big structural change (new build tooling, a new top-level folder, a renamed convention) should say, in
  the PR description, what it replaces and why the replacement earns its keep - not just what it adds. A
  reviewer (human or agent) needs that to judge whether the change is worth its cost, the same way this
  file explains why tokens are generated rather than hand-written.
