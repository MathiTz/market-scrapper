// End-to-end checks of the flows asked for in the audit, with assertions, against one running UI.
// Usage: BASE_URL=http://127.0.0.1:3000 node flows.mjs <label>
import fs from "node:fs";
import path from "node:path";

// Browsers: set PLAYWRIGHT_BROWSERS_PATH if they are not in the default location.
const { chromium, webkit } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = process.env.BASE_URL || "http://127.0.0.1:3000";
const label = process.argv[2] || "after";
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const NOW = new Date("2026-09-27T18:00:00-03:00");
const results = [];

function check(flow, step, ok, detail = "") {
  results.push({ flow, step, ok: Boolean(ok), detail: String(detail).slice(0, 300) });
  console.log(`${ok ? "PASS" : "FAIL"} [${flow}] ${step}${detail ? ` — ${String(detail).slice(0, 160)}` : ""}`);
}

async function open(browser, width, opts = {}) {
  const context = await browser.newContext({
    viewport: { width, height: width < 700 ? 844 : 900 },
    locale: "pt-BR",
    timezoneId: "America/Fortaleza",
    reducedMotion: "reduce",
    ...opts,
  });
  const page = await context.newPage();
  await page.clock.setFixedTime(NOW);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { context, page, errors };
}
const visible = (page, selector) => page.locator(selector).locator("visible=true").first();
async function ready(page) {
  await page.waitForFunction(() => !document.querySelector(".loading"), null, { timeout: 60000 });
  await page.waitForTimeout(300);
}
async function search(page, text) {
  await visible(page, 'input[aria-label="Buscar produtos"]').fill(text);
  await page.waitForTimeout(700);
  await ready(page);
}

async function flowShopping(browser, width) {
  const f = `compra-${width}`;
  const { context, page, errors } = await open(browser, width);
  await page.goto(BASE + "/");
  await ready(page);
  // Region: the snapshot covers one city; the manual reference is the address search.
  await visible(page, "button.nearby-trigger").click();
  await page.getByLabel("Endereço ou bairro em Fortaleza").fill("Aldeota");
  const suggestion = page.locator(".nearby-suggestions li button").first();
  await suggestion.waitFor({ timeout: 20000 }).catch(() => {});
  const hasSuggestion = await suggestion.count();
  check(f, "endereço manual retorna sugestões", hasSuggestion);
  if (hasSuggestion) await suggestion.click();
  await page.waitForTimeout(500);
  check(f, "referência aplicada no filtro", (await page.locator(".nearby-active").count()) > 0);
  await search(page, "lasanha bolonhesa sadia");
  const cards = await page.locator(".product-grid .product-card").count();
  check(f, "busca com resultados", cards > 0, `${cards} cartões`);
  await visible(page, 'button:has-text("Filtros")').click();
  await page.locator(".chip-row .chip", { hasText: "Sams Club" }).click();
  await page.waitForTimeout(500);
  const chip = await page.locator(".filter-chips .chip").count();
  check(f, "filtro de rede aplicado e visível (chip)", chip > 0, `${chip} chip(s)`);
  await visible(page, "button.product-open").click();
  await page.waitForTimeout(500);
  const rows = await page.locator(".offer-row").count();
  check(f, "comparação aberta", rows > 0, `${rows} linha(s)`);
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  check(f, "foco no título do produto", focused === "H1", focused);
  await page.getByRole("button", { name: /Adicionar à lista|Adicionar mais 1/ }).first().click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: /Adicionar mais 1/ }).first().click();
  await page.waitForTimeout(300);
  const status = await page.locator(".product-list-status").innerText().catch(() => "");
  check(f, "quantidade 2 no detalhe", /2 unidades/.test(status), status);
  await page.goBack();
  await page.waitForTimeout(600);
  check(f, "voltar do navegador fecha o produto e fica no app", page.url().startsWith(BASE) && (await page.locator(".product-heading").count()) === 0, page.url());
  await visible(page, 'nav button:has-text("Minha lista")').click();
  await page.waitForTimeout(400);
  await page.locator('button[aria-label^="Aumentar"]').first().click();
  await page.waitForTimeout(300);
  await page.reload();
  await ready(page);
  await visible(page, 'nav button:has-text("Minha lista")').click();
  await page.waitForTimeout(400);
  // The figure is a NumberFlow element (digits in a shadow root): read the accessibility tree instead of the text.
  const qty = await page.locator(".quantity").first().ariaSnapshot().catch(() => "");
  check(f, "quantidade editada persiste após recarregar", /3/.test(qty), qty);
  check(f, "sem erros de página", errors.length === 0, errors.join(" | "));
  await context.close();
}

async function flowFlyer(browser, width) {
  const f = `encarte-${width}`;
  const { context, page, errors } = await open(browser, width);
  await page.goto(BASE + "/");
  await ready(page);
  await visible(page, 'nav button:has-text("Encartes")').click();
  await page.waitForTimeout(800);
  await visible(page, "button.flyer-open").click();
  await page.waitForTimeout(1200);
  check(f, "leitor aberto", (await page.locator("dialog.flyer-dialog[open]").count()) === 1);
  await page.getByRole("button", { name: "Ampliar encarte" }).click();
  await page.waitForTimeout(300);
  // The percentage is a NumberFlow figure (shadow DOM): read the accessibility tree.
  const zoom = await page.locator(".flyer-zoom").ariaSnapshot().catch(() => "");
  check(f, "ampliar para 125%", zoom.replace(/\s+/g, "").includes("125"), zoom); // digits come one per node
  await page.getByRole("button", { name: "Compartilhar encarte" }).click();
  await page.waitForTimeout(600);
  const shareStatus = await page.locator(".flyer-status").innerText().catch(() => "");
  const shareLink = await page.locator(".share-link input").inputValue().catch(() => "");
  check(f, "compartilhar dá retorno (link copiado ou campo com link)", shareStatus.trim().length > 0, shareStatus || shareLink);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const back = await page.evaluate(() => document.activeElement?.className ?? "");
  check(f, "Esc fecha e devolve o foco ao botão do encarte", (await page.locator("dialog.flyer-dialog[open]").count()) === 0 && back.includes("flyer-open"), back);
  check(f, "sem erros de página", errors.length === 0, errors.join(" | "));
  await context.close();
}

async function flowGps(browser, width) {
  const f = `gps-${width}`;
  const { context, page } = await open(browser, width);
  await page.goto(BASE + "/");
  await ready(page);
  await visible(page, "button.nearby-trigger").click();
  await page.getByRole("button", { name: /Usar minha localização/ }).click();
  await page.waitForTimeout(1500);
  const message = await page.locator(".nearby-message").innerText().catch(() => "");
  check(f, "GPS negado explica e oferece endereço", /não autorizada|digitar/i.test(message), message);
  await page.getByLabel("Endereço ou bairro em Fortaleza").fill("Meireles");
  const suggestion = page.locator(".nearby-suggestions li button").first();
  await suggestion.waitFor({ timeout: 20000 }).catch(() => {});
  if (await suggestion.count()) await suggestion.click();
  await page.waitForTimeout(500);
  check(f, "endereço manual aplicado depois da recusa", (await page.locator(".nearby-active").count()) > 0);
  await context.close();
}

async function flowExpired(browser, width) {
  const f = `oferta-antiga-${width}`;
  const { context, page } = await open(browser, width);
  await page.goto(BASE + "/demo?produto=demo-detergente&oferta=d5&regiao=Fortaleza");
  await ready(page);
  await page.waitForTimeout(400);
  const notice = await page.locator("p.notice").innerText().catch(() => "");
  check(f, "link de oferta não atual avisa", notice.length > 0, notice);
  const inactive = await page.locator(".inactive-offers").innerText().catch(() => "");
  check(f, "preço antigo aparece fora da comparação com motivo", /desatualizado/i.test(inactive), inactive);
  const rows = await page.locator(".offer-row").count();
  check(f, "preço antigo não entra na comparação", rows === 0, `${rows} linha(s)`);
  await context.close();
}

async function flowBasket(browser, width) {
  const f = `cesta-${width}`;
  const { context, page } = await open(browser, width);
  await page.goto(BASE + "/");
  await ready(page);
  for (const term of ["lasanha bolonhesa sadia 600g", "cerveja skol zero zero lata 350ml", "leite xando integral"]) {
    await search(page, term);
    await visible(page, "button.add-button").click();
    await page.waitForTimeout(200);
  }
  await visible(page, 'nav button:has-text("Minha lista")').click();
  await page.waitForTimeout(500);
  const warning = await page.locator(".estimate-warning").innerText().catch(() => "");
  check(f, "aviso quando nenhuma rede cobre a lista", /Nenhuma rede/.test(warning), warning);
  const labels = await page.locator(".basket-amount small").allInnerTexts().catch(() => []);
  check(f, "subtotais rotulados como parciais", labels.length > 0 && labels.every((l) => /parcial/i.test(l)), labels.join(", "));
  const cheapest = await page.locator(".badge.good").count();
  check(f, "nenhuma rede parcial marcada como mais barata", cheapest === 0, `${cheapest}`);
  await context.close();
}

async function flowKeyboard(browser, width) {
  const f = `teclado-${width}`;
  const { context, page } = await open(browser, width);
  await page.goto(BASE + "/");
  await ready(page);
  await page.keyboard.press("Tab");
  const first = await page.evaluate(() => document.activeElement?.textContent?.trim());
  check(f, "primeiro Tab no atalho para o conteúdo", /Ir para o conteúdo/.test(first ?? ""), first);
  await visible(page, "button.store-location-trigger").focus();
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  check(f, "diálogo Onde encontrar abre pelo teclado", (await page.locator("dialog.location-dialog[open]").count()) === 1);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const back = await page.evaluate(() => document.activeElement?.className ?? "");
  check(f, "Esc fecha e devolve o foco", back.includes("store-location-trigger"), back);
  await context.close();
}

const browser = await chromium.launch();
for (const width of [390, 1280]) {
  for (const flow of [flowShopping, flowFlyer, flowGps, flowExpired, flowBasket, flowKeyboard]) {
    try {
      await flow(browser, width);
    } catch (e) {
      check(`${flow.name}-${width}`, "execução", false, String(e).split("\n")[0]);
    }
  }
}
await browser.close();
// A second engine on the main flow: WebKit emulating a phone (not a real device).
try {
  const wk = await webkit.launch();
  await flowShopping(wk, 390);
  await wk.close();
} catch (e) {
  check("webkit", "execução", false, String(e).split("\n")[0]);
}
const file = path.join(here, `flows-${label}.json`);
fs.writeFileSync(file, JSON.stringify(results, null, 2));
console.log(`${results.filter((r) => r.ok).length}/${results.length} ok -> ${file}`);
