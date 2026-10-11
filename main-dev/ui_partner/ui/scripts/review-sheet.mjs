// node scripts/review-sheet.mjs
// Writes docs/review/phase-1/index.html: every screenshot the final check saved, grouped by
// scene, light beside dark. It opens with nothing running.
import { readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dir = path.resolve(ui, "..", "docs", "review", "phase-1");
const shots = readdirSync(path.join(dir, "shots")).filter(
  (f) => f.endsWith(".png") && !f.includes("-grey") && !f.startsWith("placeholder"),
);
const groups = new Map();
for (const f of shots) {
  const m = f.match(/^(.*)-(\d+)-(light|dark)\.png$/);
  if (!m) continue;
  const key = `${m[1]}|${m[2]}`;
  if (!groups.has(key)) groups.set(key, {});
  groups.get(key)[m[3]] = f;
}
const title = (id) => id.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
const rows = [...groups.entries()]
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([key, pair]) => {
    const [id, width] = key.split("|");
    const cell = (theme) =>
      pair[theme]
        ? `<figure><img loading="lazy" src="shots/${pair[theme]}" alt="${title(id)}, ${theme}, ${width} px wide"><figcaption>${theme[0].toUpperCase() + theme.slice(1)}</figcaption></figure>`
        : "<figure></figure>";
    return `<section><h2>${title(id)} <small>${width} px wide</small></h2><div class="pair">${cell("light")}${cell("dark")}</div></section>`;
  })
  .join("\n");
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>GX10 Council: Phase 1 screenshots</title>
<style>
body{margin:0;font:16px/1.5 -apple-system,"Helvetica Neue",Arial,sans-serif;color:#17201c;background:#f3f4f2}
main{max-width:1400px;margin:0 auto;padding:32px}
h1{font-size:28px;margin:0 0 6px} h2{font-size:18px;margin:36px 0 10px} small{font-weight:400;color:#535e58;font-size:14px}
p{max-width:72ch;color:#535e58;margin:0 0 8px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px} figure{margin:0}
img{width:100%;display:block;border:1px solid #c9cfcb;border-radius:6px;background:#fff} figcaption{font-size:13px;color:#535e58;margin-top:4px}
</style></head><body><main>
<h1>GX10 Council: Phase 1 screenshots</h1>
<p>Every screen the final check looked at, light beside dark. Sample data: the question, files and answers are invented.</p>
<p>${groups.size} views of ${new Set([...groups.keys()].map((k) => k.split("|")[0])).size} screens.</p>
${rows}
</main></body></html>`;
writeFileSync(path.join(dir, "index.html"), html);
console.log(`wrote ${path.join(dir, "index.html")} (${groups.size} views)`);
