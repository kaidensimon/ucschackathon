// npm run embed-fonts -- <study.src.html> [out.html]
// The source file holds one tag naming the Fontsource CSS files it needs:
//   <style data-fonts="@fontsource-variable/archivo/wdth.css @fontsource-variable/literata/opsz.css"></style>
// This writes the fonts into that tag as embedded data and saves <name>.html beside it
// (study.src.html -> study.html). Latin subset only. It never prints font data.
// It stops with an error if a named file is missing: no substitute fonts.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = process.argv[2];
if (!src || !existsSync(src)) {
  console.error("Usage: npm run embed-fonts -- path/to/study.src.html");
  process.exit(2);
}
const out = process.argv[3] || src.replace(/\.src\.html$/, ".html");
if (out === src) {
  console.error("Source must be named *.src.html, or give an output path.");
  process.exit(2);
}
let html = readFileSync(src, "utf8");
const tag = html.match(/<style([^>]*?)data-fonts="([^"]+)"([^>]*)>[\s\S]*?<\/style>/);
if (!tag) {
  console.error('No <style data-fonts="..."></style> tag found in the source file.');
  process.exit(2);
}
const wanted = tag[2].trim().split(/\s+/);
let css = "";
let total = 0;
for (const spec of wanted) {
  const cssPath = path.join(ui, "node_modules", spec);
  if (!existsSync(cssPath)) {
    console.error(`Font CSS not found: ${spec}. Stop and report; do not substitute another font.`);
    process.exit(3);
  }
  const text = readFileSync(cssPath, "utf8");
  // Fontsource writes one block per subset, each headed by a comment such as /* archivo-latin-wdth-normal */
  const blocks = text.split(/(?=\/\*\s*[a-z0-9-]+\s*\*\/)/).filter((b) => /-latin-(?!ext)/.test(b.split("*/")[0]));
  if (!blocks.length) {
    console.error(`No latin block in ${spec}. Stop and report.`);
    process.exit(3);
  }
  for (const block of blocks) {
    const withData = block.replace(/url\((\.\/files\/[^)]+\.woff2)\)/g, (_m, rel) => {
      const file = path.join(path.dirname(cssPath), rel);
      const b64 = readFileSync(file).toString("base64");
      total += b64.length;
      return `url(data:font/woff2;base64,${b64})`;
    });
    css += withData.replace(/font-display:\s*swap/g, "font-display: block");
  }
  console.log(`embedded ${spec} (${blocks.length} latin block${blocks.length > 1 ? "s" : ""})`);
}
html = html.replace(tag[0], `<style data-fonts-embedded="${tag[2]}">\n${css}</style>`);
writeFileSync(out, html);
console.log(`wrote ${out} (${Math.round(total / 1024)} KB of font data, ${Math.round(html.length / 1024)} KB in all)`);
