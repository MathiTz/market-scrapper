// The checks battery for the design tokens (the idea comes from PrismSystem's `npm run check`):
//   node tokens/check.mjs contrast   every declared pair meets its WCAG minimum
//   node tokens/check.mjs literals   no colour literal outside tokens.css; radii only from the scale; every
//                                    var(--x) is a token (--md-*, motion) or a declared local variable
//   node tokens/check.mjs            both
// Exit code 1 on any failure, so `npm run build` refuses a regression.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const mode = process.argv[2] ?? "all";
let failures = 0;

function luminance(hex) {
  const c = hex.replace("#", "");
  const n = c.length === 3 ? c.split("").map((x) => x + x).join("") : c;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(n.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

if (mode === "contrast" || mode === "all") {
  const resolvedPath = join(here, "resolved.json");
  if (!existsSync(resolvedPath)) {
    console.error("tokens/resolved.json missing: run `npm run tokens` first");
    process.exit(1);
  }
  const { semantic, pairs } = JSON.parse(readFileSync(resolvedPath, "utf8"));
  console.log("contrast:");
  for (const [fg, bg, min] of pairs) {
    if (!(fg in semantic) || !(bg in semantic)) {
      console.log(`  ✗ unknown token in pair ${fg} / ${bg}`);
      failures++;
      continue;
    }
    const ratio = contrast(semantic[fg], semantic[bg]);
    const ok = ratio >= min;
    if (!ok) failures++;
    console.log(`  ${ok ? "✓" : "✗"} ${fg} on ${bg}: ${ratio.toFixed(2)}:1 (min ${min}:1)`);
  }
}

if (mode === "literals" || mode === "all") {
  const allow = existsSync(join(here, "allow.json")) ? JSON.parse(readFileSync(join(here, "allow.json"), "utf8")) : { files: [], lines: [] };
  const files = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(css|tsx|ts)$/.test(entry)) files.push(p);
    }
  };
  walk(join(root, "app"));
  walk(join(root, "components"));
  const radii = new Set(["6px", "10px", "14px", "20px", "999px", "50%", "0", "inherit"]);
  // Custom properties that are not tokens: set locally by a component (measurements) or by a library.
  const localVars = new Set([
    "nearby-top", "i", "x", "w", // positions and indexes written by components
    "width", // Sonner's toast width
    "transform-origin", "anchor-width", "anchor-height", "available-width", "available-height", // Base UI positioner
  ]);
  console.log("literals:");
  let found = 0;
  for (const file of files) {
    const rel = relative(root, file).replace(/\\/g, "/");
    if (rel === "app/tokens.css" || allow.files.includes(rel)) continue;
    const text = readFileSync(file, "utf8").split("\n");
    text.forEach((line, i) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")) return;
      if (allow.lines.some((s) => line.includes(s))) return;
      const problems = [];
      if (/#[0-9a-fA-F]{3,8}\b/.test(line) && !/url\(/.test(line)) problems.push("hex colour");
      if (/\b(rgba?|hsla?|oklch|oklab)\(/.test(line)) problems.push("colour function");
      const radius = /border-radius:\s*([^;]+);/.exec(line);
      if (radius) {
        const values = radius[1].trim().split(/\s+/);
        if (!values.every((v) => radii.has(v) || v.startsWith("var(") || v.startsWith("calc("))) problems.push(`radius off scale (${radius[1].trim()})`);
      }
      for (const use of line.matchAll(/var\(--([a-zA-Z0-9-]+)/g)) {
        const name = use[1];
        if (/^(md-|ease|dur-|motion-)/.test(name) || localVars.has(name)) continue;
        problems.push(`--${name} is not a token`);
      }
      if (problems.length) {
        found++;
        console.log(`  ✗ ${rel}:${i + 1} ${problems.join(", ")}: ${trimmed.slice(0, 90)}`);
      }
    });
  }
  if (found) failures += found;
  else console.log("  ✓ no colour literals or off-scale radii outside tokens.css");
}

if (failures) {
  console.error(`\n${failures} problem(s)`);
  process.exit(1);
}
console.log("\nall checks passed");
