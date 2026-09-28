// Which interactive elements show no visual change on hover (pixel comparison of the element's box, padded
// so borders, underlines and a parent card's outline count). Usage: node hover-audit.mjs <label>
import fs from "node:fs";
import path from "node:path";

// Browsers: set PLAYWRIGHT_BROWSERS_PATH if they are not in the default location.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = process.env.BASE_URL || "http://127.0.0.1:3000";
const label = process.argv[2] || "now";
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const results = [];

const CANDIDATES =
  'button:not(:disabled), a[href], summary, .chip, .segmented-option, .select-trigger, .checkbox-field, input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([readonly]), [role="tab"]';

async function audit(page, screen) {
  const items = await page.evaluate((selector) => {
    // Marks from the previous screen would collide with this one's numbering.
    for (const el of document.querySelectorAll("[data-hover-audit]")) el.removeAttribute("data-hover-audit");
    const seen = new Set();
    const out = [];
    for (const el of document.querySelectorAll(selector)) {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (!r.width || !r.height || style.visibility === "hidden" || style.display === "none") continue;
      if (el.closest("[inert], .sr-only")) continue;
      const open = document.querySelector("dialog[open]");
      if (open && !open.contains(el)) continue; // behind a modal: not hoverable
      const cls = [...el.classList].filter((c) => !["selected", "active", "in-list"].includes(c)).slice(0, 2).join(".");
      const sig = `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}${el.getAttribute("role") ? `[role=${el.getAttribute("role")}]` : ""}${el.classList.contains("selected") || el.classList.contains("active") || el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-pressed") === "true" ? ":selecionado" : ""}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      el.setAttribute("data-hover-audit", String(out.length));
      out.push({ sig, text: (el.textContent || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim().replace(/\s+/g, " ").slice(0, 40) });
    }
    return out;
  }, CANDIDATES);
  for (const [i, item] of items.entries()) {
    const handle = page.locator(`[data-hover-audit="${i}"]`);
    try {
      await handle.scrollIntoViewIfNeeded({ timeout: 2000 });
      await page.mouse.move(1, 1);
      await page.waitForTimeout(120);
      const box = await handle.boundingBox();
      if (!box) continue;
      const vp = page.viewportSize();
      const clip = {
        x: Math.max(0, box.x - 6),
        y: Math.max(0, box.y - 6),
        width: Math.min(vp.width - Math.max(0, box.x - 6), box.width + 12),
        height: Math.min(vp.height - Math.max(0, box.y - 6), box.height + 12),
      };
      if (clip.width <= 0 || clip.height <= 0) continue;
      const before = await page.screenshot({ clip });
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.waitForTimeout(250);
      const during = await page.screenshot({ clip });
      await page.mouse.move(1, 1);
      results.push({ screen, ...item, hover: !before.equals(during) });
    } catch (e) {
      results.push({ screen, ...item, hover: null, error: String(e).split("\n")[0] });
    }
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "pt-BR", reducedMotion: "reduce" });
const page = await context.newPage();
await page.clock.setFixedTime(new Date("2026-09-27T18:00:00-03:00"));
const ready = () => page.waitForFunction(() => !document.querySelector(".loading"), null, { timeout: 60000 }).then(() => page.waitForTimeout(400));
const visible = (s) => page.locator(s).locator("visible=true").first();

await page.goto(BASE + "/");
await ready();
await audit(page, "Hoje");
await visible('input[aria-label="Buscar produtos"]').fill("leite");
await page.waitForTimeout(700);
await ready();
await visible('button:has-text("Filtros")').click();
await page.waitForTimeout(300);
await page.locator(".chip-row .chip").first().click();
await page.waitForTimeout(300);
await audit(page, "Buscar + filtros");
await page.locator(".chip-row .chip").first().click();
await visible('button:has-text("Filtros")').click();
await visible('input[aria-label="Buscar produtos"]').fill("coca cola");
await page.waitForTimeout(700);
await ready();
const range = page.locator(".product-range-card button.product-open").first();
if (await range.count()) {
  await range.click();
  await page.waitForTimeout(300);
  await audit(page, "Diálogo de tamanhos");
  await page.keyboard.press("Escape");
}
await visible('input[aria-label="Buscar produtos"]').fill("lasanha bolonhesa sadia 600g");
await page.waitForTimeout(700);
await ready();
await visible("button.add-button").click();
await visible("button.product-open").click();
await page.waitForTimeout(400);
await audit(page, "Detalhe");
await visible("button.store-location-trigger").click();
await page.waitForTimeout(300);
await audit(page, "Onde encontrar");
await page.keyboard.press("Escape");
await visible('nav button:has-text("Minha lista")').click();
await page.waitForTimeout(400);
await page.locator(".basket-detail summary").first().click().catch(() => {});
await audit(page, "Minha lista");
await visible('nav button:has-text("Encartes")').click();
await page.waitForTimeout(800);
await audit(page, "Encartes");
await visible("button.flyer-open").click();
await page.waitForTimeout(1200);
await audit(page, "Leitor de encarte");
await page.keyboard.press("Escape");
await visible('nav button:has-text("Hoje")').click();
await page.waitForTimeout(300);
await visible("button.nearby-trigger").click();
await page.waitForTimeout(300);
await audit(page, "Perto de você");
await browser.close();

const file = path.join(here, `hover-${label}.json`);
fs.writeFileSync(file, JSON.stringify(results, null, 2));
const without = results.filter((r) => r.hover === false);
console.log(`${results.length} tipos de elemento verificados; ${without.length} sem mudança no hover`);
for (const r of without) console.log(`  - [${r.screen}] ${r.sig} “${r.text}”`);
console.log("com mudança:", results.filter((r) => r.hover).map((r) => `[${r.screen}] ${r.sig}`).join(" | "));
for (const r of results.filter((r) => r.hover === null)) console.log(`  ? [${r.screen}] ${r.sig}: ${r.error}`);
