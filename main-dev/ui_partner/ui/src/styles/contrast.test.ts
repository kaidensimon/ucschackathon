// FROZEN (lead). Enforces contrast on the tokens themselves, in every theme.
// Reads tokens.css, so a change to a colour that breaks a pair fails the check.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

function tokens(theme: "light" | "dark" | "warm"): Record<string, string> {
  const css = readFileSync(path.resolve(__dirname, "tokens.css"), "utf8");
  // the file holds three blocks in this order: light (plain :root), dark, warm
  const [light, rest] = css.split(':root[data-theme="dark"]');
  const [dark, warm] = (rest ?? "").split(':root[data-theme="warm"]');
  const block = theme === "light" ? light : theme === "dark" ? dark : warm;
  const out: Record<string, string> = {};
  for (const m of (block ?? "").matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) if (m[1] && m[2]) out[m[1]] = m[2];
  return out;
}
const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(c[0] ?? 0) + 0.7152 * lin(c[1] ?? 0) + 0.0722 * lin(c[2] ?? 0);
};
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};

for (const theme of ["light", "dark", "warm"] as const) {
  describe(`contrast, ${theme}`, () => {
    const t = tokens(theme);
    const get = (name: string) => {
      const v = t[name];
      if (!v) throw new Error(`token --${name} missing in ${theme}`);
      return v;
    };
    const text: [string, string][] = [
      ["ink", "page"],
      ["ink", "surface"],
      ["ink", "hover"],
      ["ink", "table"],
      ["muted", "page"],
      ["muted", "surface"],
      ["muted", "hover"],
      ["muted", "table"],
      ["on-accent", "accent"],
      ["on-accent", "accent-hover"],
      ["on-plate", "plate"],
      ["agreed", "page"],
      ["agreed", "surface"],
      ["error", "page"],
      ["error", "surface"],
      ["cv-ink", "cv-paper"],
      ["cv-grey", "cv-paper"],
    ];
    it("text is 4.5:1 or better on what it sits on", () => {
      for (const [fg, bg] of text) expect(ratio(get(fg), get(bg)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    });
    it("every seat carries its name at 4.5:1, and stands 3:1 off the page and the table", () => {
      for (let i = 1; i <= 7; i++) {
        expect(ratio(get("on-seat"), get(`seat-${i}`)), `name on seat ${i}`).toBeGreaterThanOrEqual(4.5);
        expect(ratio(get(`seat-${i}`), get("page")), `seat ${i} on page`).toBeGreaterThanOrEqual(3);
        expect(ratio(get(`seat-${i}`), get("table")), `seat ${i} on table`).toBeGreaterThanOrEqual(3);
      }
    });
    it("meaningful edges and marks are 3:1 or better", () => {
      const graphic: [string, string][] = [
        ["line", "page"],
        ["line", "surface"],
        ["line", "table"],
        ["accent", "page"],
        ["accent", "table"],
        ["cv-rule", "cv-paper"],
      ];
      for (const [fg, bg] of graphic) expect(ratio(get(fg), get(bg)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(3);
    });
    it("Chat View tokens have no colour: equal red, green and blue", () => {
      for (const name of ["cv-paper", "cv-ink", "cv-grey", "cv-rule", "cv-faint"]) {
        const v = get(name);
        expect(v.slice(1, 3) === v.slice(3, 5) && v.slice(3, 5) === v.slice(5, 7), name).toBe(true);
      }
    });
  });
}
