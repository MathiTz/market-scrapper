// Local stand-in for the read-only API, used only for this UI audit.
// - GET /api/public serves a frozen copy of the public production snapshot (downloaded once, read-only),
//   so "before" and "after" screenshots use exactly the same data.
// - GET /__mode?set=<mode> switches failure scenarios: real | 503 | 500 | slow | hang | empty.
// - /api/location and /api/location/reverse are forwarded to the production API (address search via Photon).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const PORT = Number(process.env.MOCK_PORT || 5050);
const PROD = "https://mercado-em-dia.matheusalves7894095.workers.dev";
const snapshotText = fs.readFileSync(path.join(here, "snapshot-public.json"), "utf8");
const snapshot = JSON.parse(snapshotText);
const etag = crypto.createHash("sha1").update(snapshotText).digest("hex");
let mode = process.env.MOCK_MODE || "real";
let slowMs = 4000;

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", ...headers });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

async function forward(req, res) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  try {
    const r = await fetch(PROD + req.url, {
      method: req.method,
      headers: { "Content-Type": req.headers["content-type"] || "application/json" },
      body: req.method === "GET" ? undefined : Buffer.concat(chunks),
    });
    send(res, r.status, await r.text());
  } catch {
    send(res, 502, { error: "A busca de endereço está indisponível agora. Tente de novo ou use sua localização." });
  }
}

http
  .createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    if (url.pathname === "/__mode") {
      if (url.searchParams.get("set")) mode = url.searchParams.get("set");
      if (url.searchParams.get("ms")) slowMs = Number(url.searchParams.get("ms"));
      return send(res, 200, { mode, slowMs });
    }
    if (url.pathname.startsWith("/api/location")) return forward(req, res);
    if (url.pathname === "/api/public") {
      if (mode === "503") return send(res, 503, { error: "Os dados ainda não foram publicados." }, { "Cache-Control": "no-store" });
      if (mode === "500") return send(res, 500, { error: "Não foi possível carregar as ofertas agora." });
      if (mode === "hang") return; // never answers: the UI's own 15 s timeout decides
      if (mode === "empty")
        return send(res, 200, {
          ...snapshot,
          products: [],
          offers: [],
          coverage: { networks: 0, products: 0, offers: 0, exact_pairs: 0 },
        });
      if (mode === "slow") await new Promise((r) => setTimeout(r, slowMs));
      if (req.headers["if-none-match"] === `"${etag}"`) {
        res.writeHead(304, { ETag: `"${etag}"` });
        return res.end();
      }
      return send(res, 200, snapshotText, { ETag: `"${etag}"`, "Cache-Control": "no-cache" });
    }
    if (url.pathname === "/api/session") return send(res, 200, { actor: null });
    return send(res, 404, { error: "Não encontrado." });
  })
  .listen(PORT, "127.0.0.1", () => console.log(`mock api on ${PORT}, mode=${mode}`));
