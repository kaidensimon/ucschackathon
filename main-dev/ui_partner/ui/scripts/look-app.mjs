// npm run look:app -- [--route "#/review"] [--theme warm|light|dark|both|all] [--name stem] [--out dir]
//   [--width 720 --height 520]   resize the window first (it will not go under the app's minimum)
// Opens the BUILT app (ui/dist) in the real Electron shell, looks, and closes it.
// Run `npm run build` first. Exit 1 on a console error, an attempted outside request,
// or if the window does not open. Only the lead and the verifier run this (it uses dist/).
import { existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "@playwright/test";
import { parseArgs } from "./lib/look-core.mjs";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));
if (!existsSync(path.join(ui, "dist", "index.html"))) {
  console.error("No built app. Run: npm run build");
  process.exit(2);
}
const outDir = path.resolve(args.out || path.join(ui, ".looks", "app"));
mkdirSync(outDir, { recursive: true });
const route = typeof args.route === "string" ? args.route : "";
const themes =
  !args.theme || args.theme === "both"
    ? ["light", "dark"]
    : args.theme === "all"
      ? ["warm", "light", "dark"]
      : [args.theme];
const name = args.name || (route.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "home").slice(0, 60);

// VS Code's terminal sets ELECTRON_RUN_AS_NODE, which would make Electron behave as plain Node.
const env = { ...process.env, GX10_ROUTE: route };
delete env.ELECTRON_RUN_AS_NODE;

const consoleErrors = [];
const outside = [];
const shots = [];
let code = 1;
// --packaged <path to the app's program> looks at the packaged .app instead of ui/ run through Electron
const packaged = typeof args.packaged === "string" ? path.resolve(args.packaged) : null;
// Its own profile folder: the app allows one copy at a time per profile, and the owner may have
// the real app open. The folder is thrown away afterwards.
const profile = mkdtempSync(path.join(os.tmpdir(), "gx10-look-"));
const own = `--user-data-dir=${profile}`;
const app = await electron.launch(
  packaged ? { executablePath: packaged, args: [own], env } : { args: [ui, own], cwd: ui, env },
);
try {
  const win = await app.firstWindow();
  win.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  win.on("pageerror", (e) => consoleErrors.push(e.message));
  win.on("requestfailed", (r) => {
    const u = r.url();
    if (!u.startsWith("app://gx10/") && !u.startsWith("data:") && !u.startsWith("blob:")) outside.push(u);
  });
  if (args.width && args.height) {
    const got = await app.evaluate(
      ({ BrowserWindow }, want) => {
        const w = BrowserWindow.getAllWindows()[0];
        w.setSize(want.width, want.height);
        return w.getSize();
      },
      { width: Number(args.width), height: Number(args.height) },
    );
    console.log(`WINDOW asked ${args.width} x ${args.height}, got ${got[0]} x ${got[1]}`);
    await win.waitForTimeout(300);
  }
  await win.waitForLoadState("load");
  await win.evaluate(() => document.fonts.ready.then(() => true));
  const info = await app.evaluate(({ app: a }) => ({
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    name: a.getName(),
  }));
  for (const theme of themes) {
    await win.evaluate((t) => {
      try {
        localStorage.setItem("theme", t);
      } catch {}
      document.documentElement.setAttribute("data-theme", t);
    }, theme);
    await win.waitForTimeout(200);
    const file = path.join(outDir, `${name}-${theme}.png`);
    await win.screenshot({ path: file, animations: "disabled" });
    shots.push(file);
  }
  const outline = await win.evaluate(() => ({
    title: document.title,
    shell: globalThis.gx10 ? globalThis.gx10.shell : "none",
    buttons: [...document.querySelectorAll("button,[role=button]")]
      .slice(0, 40)
      .map((b) => (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 60)),
    nodeInPage: typeof globalThis.require === "function" || typeof globalThis.process === "object",
  }));
  console.log(`ELECTRON ${info.electron} (Chromium ${info.chrome})`);
  console.log("SHOTS");
  for (const s of shots) console.log(`  ${s}`);
  console.log(`TITLE ${outline.title}`);
  console.log(`SHELL ${outline.shell}`);
  console.log(`BUTTONS ${JSON.stringify(outline.buttons)}`);
  console.log(`NODE EXPOSED TO PAGE ${outline.nodeInPage ? "YES (must be no)" : "no"}`);
  console.log(`CONSOLE ERRORS ${consoleErrors.length}`);
  for (const e of consoleErrors) console.log(`  ${e}`);
  console.log(`OUTSIDE REQUESTS ${outside.length}`);
  for (const r of outside) console.log(`  ${r}`);
  code = consoleErrors.length || outside.length || outline.nodeInPage || outline.shell !== "electron" ? 1 : 0;
} catch (e) {
  console.error(`look:app failed: ${e.message}`);
} finally {
  await app.close();
  rmSync(profile, { recursive: true, force: true });
}
process.exit(code);
