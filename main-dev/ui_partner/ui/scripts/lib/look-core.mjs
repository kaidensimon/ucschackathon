// Shared "look first" pass, after the webapp-testing skill's method:
// open the page headless, wait for it to settle, screenshot, list what is on it,
// report console errors and any request that leaves the machine. Always closes.
import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, webkit } from "@playwright/test";

export function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) out[key] = true;
      else {
        if (out[key] === undefined) out[key] = next;
        else out[key] = [].concat(out[key], next);
        i++;
      }
    } else out._.push(a);
  }
  return out;
}

const isLocal = (url, allowOrigin) => {
  if (url.startsWith("data:") || url.startsWith("blob:") || url.startsWith("about:")) return true;
  if (url.startsWith("file:")) return allowOrigin === "file";
  try {
    const u = new URL(url);
    if (allowOrigin !== "file" && u.origin === allowOrigin) return true;
    return false;
  } catch {
    return false;
  }
};

/**
 * @param {object} o
 * @param {string} o.url        page to open
 * @param {string} o.allow      "file" or an origin such as http://127.0.0.1:5311
 * @param {string} o.outDir     where screenshots go (inside the repo)
 * @param {string} o.name       file name stem
 * @param {string[]} o.themes   any of light, dark, warm
 * @param {number} o.width
 * @param {number} o.height
 * @param {number} o.scale      device scale factor (1 ordinary, 2 Retina)
 * @param {boolean} o.grey      also save a greyscale shot per theme
 * @param {boolean} o.fullPage
 * @param {string} o.browser    chromium or webkit
 * @param {string[]} o.press    keys to press before the shot
 * @param {string[]} o.click    selectors to click before the shot
 * @param {boolean} o.reducedMotion
 */
export async function look(o) {
  mkdirSync(o.outDir, { recursive: true });
  const engine = o.browser === "webkit" ? webkit : chromium;
  const browser = await engine.launch({ headless: true });
  const report = { shots: [], consoleErrors: [], outsideRequests: [], outline: null, fonts: [] };
  try {
    for (const theme of o.themes) {
      const context = await browser.newContext({
        viewport: { width: o.width, height: o.height },
        deviceScaleFactor: o.scale,
        colorScheme: theme === "dark" ? "dark" : "light",
        reducedMotion: o.reducedMotion ? "reduce" : "no-preference",
      });
      await context.addInitScript((t) => {
        try {
          localStorage.setItem("theme", t);
        } catch {}
        const set = () => document.documentElement.setAttribute("data-theme", t);
        if (document.documentElement) set();
        else document.addEventListener("readystatechange", set, { once: true });
      }, theme);
      await context.route("**/*", (route) => {
        const url = route.request().url();
        if (isLocal(url, o.allow)) return route.continue();
        report.outsideRequests.push(url);
        return route.abort();
      });
      const page = await context.newPage();
      page.on("console", (m) => {
        if (m.type() === "error") report.consoleErrors.push(`[${theme}] ${m.text()}`);
      });
      page.on("pageerror", (e) => report.consoleErrors.push(`[${theme}] ${e.message}`));
      await page.goto(o.url, { waitUntil: "load" });
      await page.waitForLoadState("networkidle").catch(() => {});
      await page.evaluate(() => document.fonts.ready.then(() => true));
      for (const key of o.press) await page.keyboard.press(key);
      for (const sel of o.click) await page.click(sel);
      if (o.press.length || o.click.length) await page.waitForTimeout(150);
      const file = path.join(o.outDir, `${o.name}-${theme}${o.scale === 1 ? "@1x" : ""}.png`);
      await page.screenshot({ path: file, fullPage: o.fullPage, animations: "disabled" });
      report.shots.push(file);
      if (o.grey) {
        await page.addStyleTag({ content: "html{filter:grayscale(1) !important}" });
        const g = path.join(o.outDir, `${o.name}-${theme}-grey.png`);
        await page.screenshot({ path: g, fullPage: o.fullPage, animations: "disabled" });
        report.shots.push(g);
      }
      if (!report.outline) {
        report.outline = await page.evaluate(() => {
          const txt = (el) =>
            (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "")
              .replace(/\s+/g, " ")
              .trim()
              .slice(0, 60);
          const pick = (sel) => [...document.querySelectorAll(sel)].slice(0, 40).map(txt);
          return {
            title: document.title,
            headings: pick("h1,h2,h3"),
            buttons: pick("button,[role=button]"),
            links: pick("a[href]"),
            inputs: [...document.querySelectorAll("input,textarea,select")]
              .slice(0, 20)
              .map((el) => el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.tagName),
          };
        });
        report.fonts = await page.evaluate(() =>
          [...document.fonts].filter((f) => f.status === "loaded").map((f) => `${f.family} ${f.weight} ${f.style}`),
        );
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  return report;
}

export function printReport(report) {
  console.log("SHOTS");
  for (const s of report.shots) console.log(`  ${s}`);
  const o = report.outline || {};
  console.log(`TITLE ${o.title || ""}`);
  console.log(`HEADINGS ${JSON.stringify(o.headings || [])}`);
  console.log(`BUTTONS ${JSON.stringify(o.buttons || [])}`);
  console.log(`LINKS ${JSON.stringify(o.links || [])}`);
  console.log(`INPUTS ${JSON.stringify(o.inputs || [])}`);
  console.log(`FONTS LOADED ${JSON.stringify([...new Set(report.fonts)])}`);
  console.log(`CONSOLE ERRORS ${report.consoleErrors.length}`);
  for (const e of report.consoleErrors) console.log(`  ${e}`);
  console.log(`OUTSIDE REQUESTS ${report.outsideRequests.length}`);
  for (const r of report.outsideRequests) console.log(`  ${r}`);
  const bad = report.consoleErrors.length + report.outsideRequests.length;
  return bad === 0 ? 0 : 1;
}

export function commonOptions(args, defaults) {
  const list = (v) => (v === undefined || v === true ? [] : [].concat(v));
  const theme = args.theme || "both";
  return {
    outDir: path.resolve(args.out || defaults.outDir),
    name: args.name || defaults.name,
    themes: theme === "both" ? ["light", "dark"] : theme === "all" ? ["warm", "light", "dark"] : [theme],
    width: Number(args.width || 1440),
    height: Number(args.height || 830),
    scale: Number(args.scale || 2),
    grey: Boolean(args.grey),
    fullPage: Boolean(args.full),
    browser: args.browser || "chromium",
    press: list(args.press),
    click: list(args.click),
    reducedMotion: Boolean(args["reduced-motion"]),
  };
}
