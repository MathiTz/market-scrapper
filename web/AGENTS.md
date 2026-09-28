# Mercado em Dia UI

A Vite + React + TypeScript single-page app. There is no Next.js here.

- Server data is fetched with TanStack React Query (`@tanstack/react-query`); keep caching and paging in query hooks rather than hand-rolled `fetch` caches.
- The UI loads one complete snapshot from `GET /api/public` and searches and filters it in the browser. Shopping lists live in `localStorage`.
- In production the API is the Hono app in `../api` (Cloudflare Workers reading Postgres). `../scraping/local_api/app.py` (Flask) serves the same routes for local development. `vite.config.ts` proxies `/api` to `API_URL` (default Flask on `http://127.0.0.1:5050`; use `http://127.0.0.1:8787` for the Hono API under `wrangler dev`). Keep both backends' routes in step.
- Routes are chosen in `app/main.tsx`: `/` (real data), `/demo` (fictional data), `/demo?vitrine=1` (the
  components sheet, every primitive in every state; never on `/`) and `/admin`.
- Design tokens live in `tokens/tokens.json` and are compiled to `app/tokens.css` by `npm run tokens` (runs
  before `dev` and `build`). Styles consume only `var(--md-*)` and the motion tokens; `npm run tokens:check`
  (also in `prebuild`) fails on colour literals, off-scale radii, unknown custom properties and contrast
  regressions. See `VISUAL.md`, `DESIGN.md` and `PLANO-UI-MOTION.md`.
- UI primitives are in `components/ui/` (Button, TextField, Chip, SelectField, Tooltip, CheckboxField,
  Segmented, skeletons, NumberFlow wrappers, `useDialog`, `useSheetDrag`, `useIndicator`). Base UI is imported
  only by `select.tsx` and `tooltip.tsx`; Sonner only by `lib/notify.tsx`; the sheet's spring in `use-sheet-drag.ts` is hand-written (no `motion`).
  Dialogs stay native `<dialog>` elements opened through `useDialog`.
- Run `npm run dev` (port 3000), `npm run typecheck`, `npm test` and `npm run build`.
