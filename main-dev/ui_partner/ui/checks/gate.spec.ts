// The final check. It walks the same scene list the review page shows.
// Built scenes get every check; a check that finds none of the thing it tests FAILS
// (so an empty page can never pass). Scenes not yet built are counted and printed.

import { mkdirSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { type Scene, scenes, themes, WINDOW } from "../src/review/states";

const SHOTS = path.resolve("../docs/review/phase-1/shots");
mkdirSync(SHOTS, { recursive: true });

// When true, every scene must be built (work packages 1.5 and 1.6).
const REQUIRE_ALL = process.env.GX10_REQUIRE_ALL === "1";

async function open(page: Page, scene: Scene, theme: string, size: { width: number; height: number }) {
  const errors: string[] = [];
  const outside: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("http://127.0.0.1:4310") || url.startsWith("data:") || url.startsWith("blob:"))
      return route.continue();
    outside.push(url);
    return route.abort();
  });
  await page.setViewportSize(size);
  await page.emulateMedia({ colorScheme: theme === "dark" ? "dark" : "light" });
  await page.addInitScript((t) => {
    try {
      localStorage.setItem("theme", t);
    } catch {}
  }, theme);
  await page.goto(`/#${scene.route}`);
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready.then(() => true));
  return { errors, outside };
}

const built = scenes.filter((s) => s.built);
const notBuilt = scenes.filter((s) => !s.built);

test("scene list: how many are built", () => {
  console.log(
    `SCENES built ${built.length}, not yet built ${notBuilt.length} (${notBuilt.map((s) => s.id).join(", ")})`,
  );
  expect(built.length).toBeGreaterThan(0);
  if (REQUIRE_ALL) expect(notBuilt.map((s) => s.id)).toEqual([]);
});

for (const scene of built) {
  const sizes = scene.onlyAt ? [scene.onlyAt] : [WINDOW, ...(scene.alsoAt ?? [])];
  for (const size of sizes) {
    for (const theme of themes) {
      test(`${scene.id} ${size.width}x${size.height} ${theme}`, async ({ page }) => {
        const { errors, outside } = await open(page, scene, theme, size);

        // 1. what must be on screen is on screen
        for (const m of scene.mustShow) {
          const n = await page.locator(m.selector).count();
          if (m.count !== undefined) expect(n, `${scene.id}: ${m.selector}`).toBe(m.count);
          if (m.atLeast !== undefined) expect(n, `${scene.id}: ${m.selector}`).toBeGreaterThanOrEqual(m.atLeast);
        }

        // 2. the theme really applied, and each font the look uses is loaded
        expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
        const fonts = await page.evaluate(() =>
          [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family),
        );
        expect(fonts.length, "at least one bundled font is loaded").toBeGreaterThan(0);

        // 3. accessibility: nothing serious or critical. One exception, by one selector:
        //    a bubble or seat part-way through a fade is faint on purpose.
        const axe = await new AxeBuilder({ page }).exclude("[data-fading=true]").analyze();
        const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(
          serious.map((v) => `${v.id}: ${v.nodes.length} node(s), e.g. ${v.nodes[0]?.html.slice(0, 120)}`),
        ).toEqual([]);

        // 4. Chat View has no colour: its panel has a solid background, and every colour
        //    that paints inside it has equal red, green and blue
        if (scene.chatView) {
          const report = await page.evaluate(() => {
            const panel = document.querySelector("[data-part=chat-view]");
            if (!panel) return { found: false, bad: [] as string[] };
            const bad: string[] = [];
            const grey = (c: string) => {
              const m = c.match(/rgba?\(([^)]+)\)/);
              const inner = m?.[1];
              if (!inner) return true;
              const [r, g, b, a] = inner.split(/[ ,/]+/).map(Number);
              if (a === 0) return true;
              return r === g && g === b;
            };
            const bg = getComputedStyle(panel).backgroundColor;
            const alpha = bg.match(/rgba\(([^)]+)\)/)?.[1]?.split(/[ ,/]+/)[3];
            if (alpha !== undefined && Number(alpha) < 1) bad.push(`panel background is see-through: ${bg}`);
            for (const el of [panel, ...panel.querySelectorAll("*")]) {
              const cs = getComputedStyle(el);
              const props = [
                "color",
                "backgroundColor",
                "borderTopColor",
                "borderRightColor",
                "borderBottomColor",
                "borderLeftColor",
                "outlineColor",
                "textDecorationColor",
                "caretColor",
                "fill",
                "stroke",
              ] as const;
              for (const p of props) {
                const v = cs[p];
                if (typeof v === "string" && v.startsWith("rgb") && !grey(v))
                  bad.push(`${el.tagName.toLowerCase()} ${p} ${v}`);
              }
              if (cs.boxShadow && cs.boxShadow !== "none") {
                for (const m of cs.boxShadow.match(/rgba?\([^)]+\)/g) ?? [])
                  if (!grey(m)) bad.push(`${el.tagName.toLowerCase()} shadow ${m}`);
              }
            }
            return { found: true, bad: bad.slice(0, 10) };
          });
          expect(report.found, "a Chat View scene must show the Chat View panel").toBe(true);
          expect(report.bad).toEqual([]);
        }

        // 5. colour is never the only signal: every seat shows its name as text
        if (scene.table) {
          const seats = page.locator("[data-part=seat]");
          const count = await seats.count();
          expect(count, "a table scene must show seats").toBeGreaterThan(0);
          for (let i = 0; i < count; i++) {
            const name = (await seats.nth(i).locator("[data-part=seat-name]").textContent())?.trim() ?? "";
            expect(name.length, `seat ${i} shows its name`).toBeGreaterThan(0);
            expect(
              (await seats.nth(i).getAttribute("aria-label"))?.length ?? 0,
              `seat ${i} has a spoken name`,
            ).toBeGreaterThan(0);
          }
        }

        // 6. screenshots, for eyes (nothing is compared pixel by pixel in Phase 1)
        const stem = `${scene.id}-${size.width}-${theme}`;
        await page.screenshot({ path: path.join(SHOTS, `${stem}.png`), animations: "disabled" });
        if (scene.table) {
          await page.addStyleTag({ content: "html{filter:grayscale(1) !important}" });
          await page.screenshot({ path: path.join(SHOTS, `${stem}-grey.png`), animations: "disabled" });
        }

        // 7. nothing left the machine, and the console is clean
        expect(outside, "requests to another origin").toEqual([]);
        expect(errors, "console errors").toEqual([]);
      });
    }
  }
}
