// npm run contrast -- <pairs.json> [--report]
// pairs.json: { "name": "...", "pairs": [ { "pair": "text on page", "theme": "light",
//   "fg": "#1D2427", "bg": "#E9ECE8", "min": 4.5 } ] }
// Optional per pair: "alpha" (0-1, fg drawn at that opacity over bg).
// Prints every ratio. Exit 1 if any pair is below its "min", unless --report.
import { readFileSync } from "node:fs";

export function luminance(hex) {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(n.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function mix(fg, bg, alpha) {
  const p = (hex) => {
    const h = hex.replace("#", "");
    return [0, 2, 4].map((i) => Number.parseInt(h.slice(i, i + 2), 16));
  };
  const [f, b] = [p(fg), p(bg)];
  return `#${f
    .map((c, i) =>
      Math.round(c * alpha + b[i] * (1 - alpha))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export function ratio(fg, bg) {
  const [a, b] = [luminance(fg), luminance(bg)];
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const file = process.argv[2];
  const reportOnly = process.argv.includes("--report");
  if (!file) {
    console.error("Usage: npm run contrast -- path/to/pairs.json [--report]");
    process.exit(2);
  }
  const data = JSON.parse(readFileSync(file, "utf8"));
  let fails = 0;
  console.log(`CONTRAST ${data.name || file}`);
  for (const p of data.pairs) {
    const fg = p.alpha !== undefined ? mix(p.fg, p.bg, p.alpha) : p.fg;
    const r = ratio(fg, p.bg);
    const ok = r >= p.min;
    if (!ok) fails++;
    console.log(
      `  ${ok ? "ok  " : "FAIL"} ${r.toFixed(2).padStart(5)}:1  need ${String(p.min).padEnd(4)} [${p.theme || "-"}] ${p.pair}  (${p.fg} on ${p.bg})`,
    );
  }
  console.log(`${data.pairs.length} pairs, ${fails} below threshold`);
  process.exit(fails && !reportOnly ? 1 : 0);
}
