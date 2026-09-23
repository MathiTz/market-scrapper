# Mercado em Dia UI

A Vite + React + TypeScript single-page app. There is no Next.js here.

- Server data is fetched with TanStack React Query (`@tanstack/react-query`); keep caching and paging in query hooks rather than hand-rolled `fetch` caches.
- The UI loads one complete snapshot from `GET /api/public` and searches and filters it in the browser. Shopping lists live in `localStorage`.
- In production the API is the Hono app in `../api` (Cloudflare Workers reading Postgres). `../scraping/local_api/app.py` (Flask) serves the same routes for local development. `vite.config.ts` proxies `/api` to `API_URL` (default Flask on `http://127.0.0.1:5050`; use `http://127.0.0.1:8787` for the Hono API under `wrangler dev`). Keep both backends' routes in step.
- Routes are chosen in `app/main.tsx`: `/` (real data), `/demo` (fictional data) and `/admin`.
- Run `npm run dev` (port 3000), `npm run typecheck` and `npm run build`.
