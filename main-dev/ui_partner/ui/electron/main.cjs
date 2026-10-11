// Electron shell for Syndicate.
//
// The window loads the app's own built files from app://gx10/ and nothing else. The page has
// no Node access and never talks to the network. This build is UI only: there is no engine
// and no model, and nothing is started besides the window.
const { app, BrowserWindow, ipcMain, Menu, protocol, session, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

const DEV_URL = process.env.GX10_DEV_URL || ""; // e.g. http://127.0.0.1:5311 while developing
const START_ROUTE = process.env.GX10_ROUTE || ""; // e.g. #/review
const DIST = path.join(__dirname, "..", "dist");
const ORIGIN = "app://gx10";

// ---- one copy of the app at a time ----
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);

// ---- serving the app's own files ----
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".txt": "text/plain; charset=utf-8",
  ".map": "application/json; charset=utf-8",
};

// Only the app's own files may run or load. No inline scripts; styles may be inline because
// positions on the table are set that way.
const CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  // the council engine on this computer (the UI falls back to its mock when it is not running)
  "connect-src 'self' http://127.0.0.1:8765",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

function serveFile(url) {
  let rel = decodeURIComponent(url.pathname);
  if (rel === "/" || rel === "") rel = "/index.html";
  const file = path.normalize(path.join(DIST, rel));
  // never serve anything outside the app's own folder
  if (!file.startsWith(DIST + path.sep)) return new Response("Not found", { status: 404 });
  try {
    const body = fs.readFileSync(file);
    return new Response(body, {
      headers: {
        "content-type": TYPES[path.extname(file).toLowerCase()] || "application/octet-stream",
        "content-security-policy": CSP,
        "x-content-type-options": "nosniff",
        "cache-control": "no-store",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}

function isAllowed(url) {
  if (url.startsWith(`${ORIGIN}/`) || url.startsWith("data:") || url.startsWith("blob:")) return true;
  if (url.startsWith("devtools:") || url.startsWith("chrome-extension:")) return true;
  if (url.startsWith("http://127.0.0.1:8765/")) return true; // the council engine
  if (DEV_URL) {
    try {
      const u = new URL(url);
      const d = new URL(DEV_URL);
      if (u.host === d.host) return true; // http and its ws hot-reload channel
    } catch {}
  }
  return false;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    // the council's figures shrink with the window, so it may be made this small
    minWidth: 800,
    minHeight: 600, // the title bar is part of this
    title: "Syndicate",
    backgroundColor: "#FFFFFF",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });
  win.once("ready-to-show", () => win.show());
  // No new windows, no leaving the app. A real web link opens in the computer's browser only if it is https.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAllowed(url)) event.preventDefault();
  });
  if (DEV_URL) win.loadURL(`${DEV_URL}/${START_ROUTE}`);
  else win.loadURL(`${ORIGIN}/index.html${START_ROUTE}`);
  return win;
}

app.on("second-instance", () => {
  const [win] = BrowserWindow.getAllWindows();
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

// ---- "Web search" switch ----
// One plain search in a hidden window of its own (its own session, so the rule that the app's page
// may only load the app's files stays as strict as before). The window loads the results page of a
// search site, the titles and short descriptions of the first results are read off it, and the
// window is closed. No link is followed. Only the owner's question leaves this computer, and only
// when the switch is on.
const SEARCH_PAGES = [
  {
    url: (q) => `https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}`,
    read: `[...document.querySelectorAll(".result")].map((r) => ({
      title: (r.querySelector(".result__a") || {}).innerText || "",
      url: (r.querySelector(".result__url") || {}).innerText || "",
      snippet: (r.querySelector(".result__snippet") || {}).innerText || "",
    }))`,
  },
  {
    url: (q) => `https://www.bing.com/search?q=${encodeURIComponent(q)}`,
    read: `[...document.querySelectorAll("li.b_algo")].map((r) => ({
      title: (r.querySelector("h2") || {}).innerText || "",
      url: (r.querySelector("cite") || {}).innerText || "",
      snippet: (r.querySelector("p") || {}).innerText || "",
    }))`,
  },
];

async function readSearchPage(page, query) {
  const win = new BrowserWindow({
    show: false,
    width: 1200,
    height: 900,
    webPreferences: { partition: "gx10-search", contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  try {
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    win.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    win.webContents.session.on("will-download", (event) => event.preventDefault());
    await Promise.race([
      win.loadURL(page.url(query)),
      new Promise((_resolve, reject) => setTimeout(() => reject(new Error("search page took too long")), 12000)),
    ]);
    await new Promise((resolve) => setTimeout(resolve, 600));
    const found = await win.webContents.executeJavaScript(page.read, true);
    return (Array.isArray(found) ? found : [])
      .map((r) => ({
        title: String(r.title || "").trim().slice(0, 160),
        url: String(r.url || "").trim().slice(0, 300),
        snippet: String(r.snippet || "").trim().slice(0, 400),
      }))
      .filter((r) => r.title)
      .slice(0, 5);
  } catch {
    return [];
  } finally {
    if (!win.isDestroyed()) win.destroy();
  }
}

ipcMain.handle("gx10:web-search", async (_event, question) => {
  const query = String(question || "").split("\n")[0].replace(/\s+/g, " ").trim().slice(0, 200);
  if (!query) return [];
  for (const page of SEARCH_PAGES) {
    const found = await readSearchPage(page, query);
    if (found.length > 0) return found;
  }
  return [];
});

app.whenReady().then(() => {
  if (process.platform !== "darwin") Menu.setApplicationMenu(null);

  protocol.handle("app", (request) => {
    const url = new URL(request.url);
    if (url.host !== "gx10") return new Response("Not found", { status: 404 });
    return serveFile(url);
  });

  // nothing but the app's own pages may be requested
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: !isAllowed(details.url) });
  });
  // The page may copy text to the clipboard (the Copy button). Every other permission is refused.
  const own = (wc) => {
    try {
      return new URL(wc.getURL()).origin === ORIGIN || (DEV_URL && wc.getURL().startsWith(DEV_URL));
    } catch {
      return false;
    }
  };
  session.defaultSession.setPermissionRequestHandler((wc, permission, callback) => {
    callback(permission === "clipboard-sanitized-write" && own(wc));
  });
  session.defaultSession.setPermissionCheckHandler((wc, permission) => permission === "clipboard-sanitized-write" && Boolean(wc) && own(wc));

  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => app.quit());
