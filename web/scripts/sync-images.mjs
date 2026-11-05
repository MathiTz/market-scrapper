/**
 * Copy the mirrored product images the current payload refers to into `public/`, so the Worker serves
 * them from its own assets.
 *
 * `scraping/images/` is generated and gitignored; the payload only references a mirror file when the
 * chain's own URL is dead (see `scraping/services/image_health.py`). The publisher writes the list it
 * used to `scraping/data/image-manifest.json`, and this script mirrors exactly that list - not the
 * whole 33 MiB collection - into `public/images/`, which Vite copies into `dist/`.
 *
 * Run automatically before `dev` and `build`. With no manifest (a fresh checkout that has never
 * published) it warns and does nothing: the payload will still be pointing at the chains' URLs.
 */
import { cp, mkdir, readFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = resolve(root, "../scraping/data/image-manifest.json");
const scraping = resolve(root, "../scraping");
const target = join(root, "public", "images");

let paths;
try {
  paths = JSON.parse(await readFile(manifestPath, "utf8"));
} catch {
  console.warn(`images: no manifest at ${manifestPath}; run the publisher first (skipping)`);
  process.exit(0);
}
if (!Array.isArray(paths)) {
  console.warn("images: manifest is not a list of paths (skipping)");
  process.exit(0);
}

await rm(target, { recursive: true, force: true });
let copied = 0;
const missing = [];
for (const path of paths) {
  // "images/ae/<sha>.webp" in the manifest; served as /images/ae/<sha>.webp
  try {
    const to = join(root, "public", path);
    await mkdir(dirname(to), { recursive: true });
    await cp(join(scraping, path), to);
    copied += 1;
  } catch {
    missing.push(path);
  }
}
console.log(`images: ${copied} copied${missing.length ? `, ${missing.length} missing` : ""}`);
if (missing.length) console.warn(`images: missing from scraping/, e.g. ${missing.slice(0, 3).join(", ")}`);
