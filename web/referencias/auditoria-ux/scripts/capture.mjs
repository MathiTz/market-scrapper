// Before/after captures of the Mercado em Dia UI, same data (frozen snapshot via mock-api.mjs), same widths,
// same fixed clock. Usage: node capture.mjs <label> [--only name1,name2]
import fs from "node:fs";
import path from "node:path";

// Browsers: set PLAYWRIGHT_BROWSERS_PATH if they are not in the default location.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");

const label = process.argv[2] || "before";
const only = (process.argv.find((a) => a.startsWith("--only=")) || "").slice(7).split(",").filter(Boolean);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const out = path.join(here, "shots", label);
fs.mkdirSync(out, { recursive: true });
const BASE = process.env.BASE_URL || "http://127.0.0.1:3000";
const MOCK = "http://127.0.0.1:5050";
// Fixed "now": 6 h after the frozen snapshot was generated (12:04 in Fortaleza), inside every offer's 36 h TTL.
const NOW = new Date("2026-09-27T18:00:00-03:00");
const WIDTHS = { 320: 568, 390: 844, 768: 1024, 1280: 800 };
const report = [];

async function mode(m, ms) {
  await fetch(`${MOCK}/__mode?set=${m}${ms ? `&ms=${ms}` : ""}`);
}

async function newPage(browser, width, { offline = false } = {}) {
  const context = await browser.newContext({
    viewport: { width, height: WIDTHS[width] },
    deviceScaleFactor: 1,
    locale: "pt-BR",
    timezoneId: "America/Fortaleza",
    reducedMotion: "reduce", // freezes the flyer auto-advance so captures are comparable
  });
  const page = await context.newPage();
  await page.clock.setFixedTime(NOW);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  return { context, page, errors };
}

async function waitData(page) {
  await page.waitForFunction(() => !document.querySelector(".loading"), null, { timeout: 60000 });
  await page.waitForTimeout(400);
}

async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

async function shot(page, name, width, opts = {}) {
  const file = path.join(out, `${width}-${name}.png`);
  let style;
  if (opts.full) {
    // Lazy images only load near the viewport: walk the page once so the full capture shows them.
    await page.evaluate(async () => {
      const start = window.scrollY;
      for (let y = 0; y < document.body.scrollHeight; y += Math.max(300, window.innerHeight * 0.8)) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 120));
      }
      window.scrollTo(0, start);
    });
    await page.waitForTimeout(500);
    // The fixed mobile dock would be painted in the middle of a full-page capture; viewport captures keep it.
    style = await page.addStyleTag({ content: ".mobile-dock{visibility:hidden!important}" });
  }
  await page.screenshot({ path: file, fullPage: !!opts.full, animations: "disabled" });
  if (style) await style.evaluate((node) => node.remove());
  report.push({ name, width, file: path.basename(file), overflowPx: await overflow(page) });
}

const visible = (page, selector) => page.locator(selector).locator("visible=true").first();

async function search(page, text) {
  const box = visible(page, 'input[aria-label="Buscar produtos"]');
  await box.fill(text);
  await page.waitForTimeout(700);
  await waitData(page);
}

async function nav(page, text) {
  await visible(page, `nav button:has-text("${text}")`).click();
  await page.waitForTimeout(300);
}

const scenarios = {
  // Home, top of the page and the whole page.
  async hoje(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await shot(page, "hoje-topo", width);
    await shot(page, "hoje-completa", width, { full: true });
    report.at(-1).errors = errors;
    await context.close();
  },
  // The components sheet (plan 009): every primitive in every state, on the demo route only.
  async vitrine(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/demo?vitrine=1");
    await page.waitForTimeout(800);
    await shot(page, "vitrine", width, { full: true });
    report.at(-1).errors = errors;
    await context.close();
  },
  // Search: typed term, filters open, no results.
  async busca(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "leite integral");
    await shot(page, "busca-leite", width);
    await visible(page, 'button:has-text("Filtros")').click();
    await page.waitForTimeout(200);
    await shot(page, "busca-filtros", width);
    await search(page, "xyzqw");
    await shot(page, "busca-sem-resultado", width);
    report.at(-1).errors = errors;
    await context.close();
  },
  // Detail page: a real three-chain comparison and the suspicious one featured on the home page.
  async comparacao(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "lasanha bolonhesa sadia 600g");
    await visible(page, "button.product-open").click();
    await page.waitForTimeout(400);
    await shot(page, "comparacao", width);
    await shot(page, "comparacao-completa", width, { full: true });
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "laranja pera 18kg");
    await visible(page, "button.product-open").click();
    await page.waitForTimeout(400);
    await shot(page, "comparacao-suspeita", width, { full: true });
    report.at(-1).errors = errors;
    await context.close();
  },
  // A card that groups several sizes, and its dialog.
  async tamanhos(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "coca cola");
    await shot(page, "tamanhos-card", width);
    const range = page.locator(".product-range-card button.product-open").locator("visible=true").first();
    if (await range.count()) {
      await range.click();
      await page.waitForTimeout(300);
      await shot(page, "tamanhos-dialogo", width);
    }
    report.at(-1).errors = errors;
    await context.close();
  },
  // List: three products added from search, then the list with estimates.
  async lista(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    for (const term of ["lasanha bolonhesa sadia 600g", "cerveja skol zero zero lata 350ml", "leite integral"]) {
      await search(page, term);
      await visible(page, "button.add-button").click();
      await page.waitForTimeout(250);
    }
    await nav(page, "Minha lista");
    await waitData(page);
    await shot(page, "lista", width);
    await shot(page, "lista-completa", width, { full: true });
    await page.reload();
    await waitData(page);
    await nav(page, "Minha lista");
    report.push({ name: "lista-apos-recarregar", width, items: await page.locator(".list-item").count() });
    report.at(-1).errors = errors;
    await context.close();
  },
  // Flyers: the page and the reader.
  async encartes(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await nav(page, "Encartes");
    await page.waitForTimeout(1200);
    await shot(page, "encartes", width);
    await visible(page, "button.flyer-open").click();
    await page.waitForTimeout(1500);
    await shot(page, "encarte-leitor", width);
    report.at(-1).errors = errors;
    await context.close();
  },
  // Location: the "Perto de você" dialog and a card's "Ver localização".
  async local(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await visible(page, "button.nearby-trigger").click();
    await page.waitForTimeout(300);
    await shot(page, "local-dialogo", width);
    await page.keyboard.press("Escape");
    await visible(page, "button.store-location-trigger").click();
    await page.waitForTimeout(300);
    await shot(page, "ver-localizacao", width);
    report.at(-1).errors = errors;
    await context.close();
  },
  // System states: loading, API down, empty snapshot, offline after loading.
  async estados(browser, width) {
    let { context, page, errors } = await newPage(browser, width);
    await mode("slow", 6000);
    await page.goto(BASE + "/");
    await page.waitForTimeout(1500);
    await shot(page, "estado-carregando", width);
    await context.close();
    await mode("503");
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await page.waitForTimeout(2500);
    await shot(page, "estado-erro-503", width);
    await nav(page, "Buscar");
    await page.waitForTimeout(300);
    await shot(page, "estado-erro-503-busca", width);
    await context.close();
    await mode("empty");
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await waitData(page);
    await shot(page, "estado-snapshot-vazio", width);
    await context.close();
    await mode("real");
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await waitData(page);
    await context.setOffline(true);
    await page.waitForTimeout(500);
    await shot(page, "estado-offline", width);
    await nav(page, "Minha lista");
    await shot(page, "estado-offline-lista", width);
    await context.close();
    await mode("real");
  },
  // Demo route: fictional data, including an outdated price (only listed with "sem preço atual" on).
  async demo(browser, width) {
    const { context, page, errors } = await newPage(browser, width);
    await page.goto(BASE + "/demo");
    await waitData(page);
    await shot(page, "demo-hoje", width);
    // The only fictional price of "Detergente" is 48 h old: searching for it, with the filters open.
    await search(page, "detergente");
    await visible(page, 'button:has-text("Filtros")').click();
    await page.waitForTimeout(300);
    const toggle = page.getByLabel(/Incluir produtos sem preço atual/);
    report.push({ name: "demo-opcao-sem-preco-visivel", width, visible: await toggle.count() });
    if (await toggle.count()) {
      await toggle.check();
      await page.waitForTimeout(300);
    }
    await shot(page, "demo-busca-preco-antigo", width, { full: true });
    // Its product page, opened by link (the way a shared link would reach it).
    await page.goto(BASE + "/demo?produto=demo-detergente");
    await waitData(page);
    await page.waitForTimeout(300);
    await shot(page, "demo-preco-antigo", width, { full: true });
    report.at(-1).errors = errors;
    await context.close();
  },
  // Links, conditions, filters, focus, storage and offline with a list.
  async extras(browser, width) {
    let { context, page, errors } = await newPage(browser, width);
    // A shared link to a current offer, and one to a product that no longer exists.
    await page.goto(BASE + "/?produto=324&oferta=324-1&regiao=Fortaleza");
    await waitData(page);
    await page.waitForTimeout(500);
    await shot(page, "link-oferta", width);
    await page.goto(BASE + "/?produto=nao-existe&oferta=x&regiao=Fortaleza");
    await waitData(page);
    await shot(page, "link-inexistente", width);
    // A club price: with and without "Incluir clube".
    await page.goto(BASE + "/?produto=2150&oferta=2150-15-club&regiao=Fortaleza");
    await waitData(page);
    await page.waitForTimeout(500);
    await shot(page, "clube-incluido", width, { full: true });
    // Filters that exclude everything.
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "leite");
    await visible(page, 'button:has-text("Filtros")').click();
    await visible(page, 'input[inputmode="decimal"]').fill("9999");
    await page.waitForTimeout(500);
    await shot(page, "filtros-sem-resultado", width, { full: true });
    // Keyboard focus on the home page.
    await page.goto(BASE + "/");
    await waitData(page);
    for (let i = 0; i < 4; i++) await page.keyboard.press("Tab");
    await shot(page, "foco-teclado", width);
    // Back button after opening a product from search.
    await search(page, "lasanha bolonhesa sadia 600g");
    await visible(page, "button.product-open").click();
    await page.waitForTimeout(300);
    await page.goBack();
    await page.waitForTimeout(800);
    report.push({ name: "voltar-do-navegador", width, url: page.url(), onProduct: await page.locator(".product-heading").count() });
    await context.close();
    // A list saved in a form this version cannot read.
    ({ context, page, errors } = await newPage(browser, width));
    await context.addInitScript(() => {
      if (!sessionStorage.getItem("seeded")) {
        localStorage.setItem("med-list-real", "{corrompido");
        sessionStorage.setItem("seeded", "1");
      }
    });
    await page.goto(BASE + "/");
    await waitData(page);
    await nav(page, "Minha lista");
    await page.waitForTimeout(500);
    await shot(page, "lista-armazenamento-ilegivel", width);
    report.push({ name: "lista-armazenamento-ilegivel", width, stored: await page.evaluate(() => localStorage.getItem("med-list-real")) });
    await context.close();
    // Offline with a list: the list view and a product page.
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await waitData(page);
    for (const term of ["lasanha bolonhesa sadia 600g", "cerveja skol zero zero lata 350ml"]) {
      await search(page, term);
      await visible(page, "button.add-button").click();
      await page.waitForTimeout(200);
    }
    await context.setOffline(true);
    await page.waitForTimeout(300);
    await nav(page, "Minha lista");
    await shot(page, "offline-lista-com-itens", width, { full: true });
    await nav(page, "Buscar");
    await search(page, "lasanha bolonhesa sadia 600g");
    await shot(page, "offline-busca", width);
    await context.close();
    // GPS refused.
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await waitData(page);
    await visible(page, "button.nearby-trigger").click();
    await page.getByRole("button", { name: /Usar minha localização/ }).click();
    await page.waitForTimeout(1500);
    await shot(page, "gps-negado", width);
    await context.close();
    // An address typed by hand (forwarded to the address search) and a radius.
    ({ context, page, errors } = await newPage(browser, width));
    await page.goto(BASE + "/");
    await waitData(page);
    await visible(page, "button.nearby-trigger").click();
    await page.getByLabel("Endereço ou bairro em Fortaleza").fill("Aldeota");
    const suggestion = page.locator(".nearby-suggestions li button").first();
    await suggestion.waitFor({ timeout: 20000 });
    await shot(page, "endereco-sugestoes", width);
    await suggestion.click();
    await page.waitForTimeout(600);
    await shot(page, "hoje-com-referencia", width);
    await search(page, "lasanha bolonhesa sadia 600g");
    await shot(page, "busca-com-referencia", width);
    await visible(page, "button.product-open").click();
    await page.waitForTimeout(300);
    await shot(page, "comparacao-com-referencia", width, { full: true });
    report.push({ name: "extras", width, errors });
    await context.close();
  },
  // Empty results with the filter panel closed: a term nothing matches, then filters that exclude everything.
  async vazios(browser, width) {
    const { context, page } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await search(page, "xyzqw");
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "vazio-termo", width, { full: true });
    await search(page, "leite");
    await visible(page, 'button:has-text("Filtros")').click();
    await visible(page, 'input[inputmode="decimal"]').fill("9999");
    await page.waitForTimeout(400);
    await visible(page, 'button:has-text("Filtros")').click();
    await page.waitForTimeout(300);
    await shot(page, "vazio-filtros", width, { full: true });
    await context.close();
  },
  // Removing a list item, and what is left to recover it.
  async remocao(browser, width) {
    const { context, page } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    for (const term of ["lasanha bolonhesa sadia 600g", "cerveja skol zero zero lata 350ml"]) {
      await search(page, term);
      await visible(page, "button.add-button").click();
      await page.waitForTimeout(200);
    }
    await nav(page, "Minha lista");
    await page.locator('button[aria-label^="Remover"]').first().click();
    await page.waitForTimeout(400);
    await shot(page, "lista-apos-remover", width);
    // The list notice and the toast both offer it: the first one (the notice) is enough to check.
    const undoButton = page.getByRole("button", { name: /Desfazer/ }).first();
    report.push({ name: "lista-desfazer-disponivel", width, available: await undoButton.count() });
    if (await undoButton.count()) {
      await undoButton.click();
      await page.waitForTimeout(300);
      report.push({ name: "lista-apos-desfazer", width, items: await page.locator(".list-item").count() });
    }
    await context.close();
  },
  // The API never answers: the UI's own 15 s timeout (and React Query's one retry) decides.
  async timeout(browser, width) {
    const { context, page } = await newPage(browser, width);
    await mode("hang");
    await page.goto(BASE + "/");
    await page.waitForFunction(() => !document.querySelector(".loading"), null, { timeout: 70000 });
    await page.waitForTimeout(300);
    await shot(page, "estado-timeout", width);
    report.push({ name: "estado-timeout-texto", width, text: (await page.locator(".notice, .status-panel").allInnerTexts()).join(" | ") });
    await mode("real");
    await context.close();
  },
  // Losing the connection with data loaded, then getting it back.
  async conexao(browser, width) {
    const { context, page } = await newPage(browser, width);
    await page.goto(BASE + "/");
    await waitData(page);
    await context.setOffline(true);
    await page.waitForTimeout(400);
    const offlineCards = await page.locator(".offer-rail .product-card").count();
    await context.setOffline(false);
    await page.waitForTimeout(800);
    await shot(page, "conexao-retomada", width);
    report.push({
      name: "conexao",
      width,
      offlineCards,
      onlineCards: await page.locator(".offer-rail .product-card").count(),
      notices: (await page.locator(".notice").allInnerTexts()).join(" | "),
    });
    await context.close();
  },
  async admin(browser, width) {
    const { context, page } = await newPage(browser, width);
    await page.goto(BASE + "/admin");
    await page.waitForTimeout(1500);
    await shot(page, "admin", width);
    await context.close();
  },
};

const plan = {
  hoje: [320, 390, 768, 1280],
  vitrine: [390, 1280],
  busca: [320, 390, 768, 1280],
  comparacao: [320, 390, 768, 1280],
  tamanhos: [390, 1280],
  lista: [320, 390, 768, 1280],
  encartes: [320, 390, 768, 1280],
  local: [390, 1280],
  estados: [390, 1280],
  demo: [390, 1280],
  extras: [390, 1280],
  admin: [390],
  vazios: [390, 1280],
  remocao: [390],
  timeout: [390],
  conexao: [390],
};

const browser = await chromium.launch();
await mode("real");
for (const [name, widths] of Object.entries(plan)) {
  if (only.length && !only.includes(name)) continue;
  for (const width of widths) {
    try {
      await scenarios[name](browser, width);
      console.log("ok", name, width);
    } catch (e) {
      console.log("FAIL", name, width, String(e).split("\n")[0]);
      report.push({ name, width, failed: String(e).split("\n")[0] });
      await mode("real");
    }
  }
}
await browser.close();
const reportFile = path.join(out, `report${only.length ? "-" + only.join("-") : ""}.json`);
fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
console.log("report", reportFile);
