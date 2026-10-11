// npm run token-guard
// Every colour and size comes from src/styles/tokens.css. This fails the check when a
// source file reaches round the tokens:
//   - a raw colour (#abc, #aabbcc, rgb(), hsl(), oklch()) outside src/styles/
//   - a Tailwind value in square brackets, e.g. w-[412px] or text-[#333]
//     (state variants such as data-[state=open]: and aria-[current=page]: are allowed)
//   - a gradient or an uppercase transform (both ruled out by every candidate look)
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(ui, "src");
const skip = [path.join(src, "styles"), path.join(src, "fixtures")];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (skip.some((s) => p.startsWith(s))) continue;
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (/\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name)) yield p;
  }
}

const rules = [
  { name: "raw colour", re: /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(/g },
  {
    name: "bracketed Tailwind value",
    re: /(?<![a-z-])(?!data-|aria-|group-|peer-|has-|not-|supports-|nth-)[a-z][a-z0-9-]*-\[[^\]]+\]/g,
  },
  { name: "gradient", re: /\b(?:bg-gradient|bg-linear|bg-radial|linear-gradient|radial-gradient)\b/g },
  { name: "uppercase", re: /\buppercase\b|text-transform:\s*uppercase/g },
];

let bad = 0;
for (const file of walk(src)) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    if (line.includes("token-guard-allow")) return;
    for (const rule of rules) {
      const hits = line.match(rule.re);
      if (!hits) continue;
      bad += hits.length;
      console.log(`${path.relative(ui, file)}:${i + 1}  ${rule.name}: ${hits.join(", ")}`);
    }
  });
}
console.log(bad ? `TOKEN GUARD: ${bad} problem${bad > 1 ? "s" : ""}` : "TOKEN GUARD: clean");
process.exit(bad ? 1 : 0);
