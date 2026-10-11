// Loads the built UI in a hidden Electron window and reports whether the page reached the council
// backend. Prints one JSON line and exits 0 when linked, 1 when not.
//   cd ui_partner/ui && DISPLAY=:1 npx electron ../../tools/box/ui_link_check.cjs
const { app, BrowserWindow, session } = require("electron");

const UI = process.env.UI_URL || "http://127.0.0.1:4173";
const ENGINE = process.env.ENGINE_URL || "http://127.0.0.1:8765";

app.whenReady().then(async () => {
  const seen = [];
  session.defaultSession.webRequest.onCompleted({ urls: [`${ENGINE}/*`] }, (d) => {
    seen.push({ url: d.url.replace(ENGINE, ""), status: d.statusCode });
  });
  const failed = [];
  session.defaultSession.webRequest.onErrorOccurred({ urls: [`${ENGINE}/*`] }, (d) => {
    failed.push({ url: d.url.replace(ENGINE, ""), error: d.error });
  });
  const win = new BrowserWindow({ show: false, width: 1280, height: 800 });
  const errors = [];
  win.webContents.on("console-message", (_e, level, message) => {
    if (level >= 2) errors.push(String(message).slice(0, 200));
  });
  await win.loadURL(UI);
  await new Promise((r) => setTimeout(r, 7000));
  const title = await win.webContents.executeJavaScript("document.title");
  const text = await win.webContents.executeJavaScript("document.body.innerText.slice(0, 300)");
  const health = seen.find((s) => s.url.startsWith("/ui/health") && s.status === 200);
  const chats = seen.find((s) => s.url.startsWith("/ui/chats") && s.status === 200);
  const linked = Boolean(health && chats);
  console.log(JSON.stringify({ linked, title, requests: seen.slice(0, 12), failed, errors: errors.slice(0, 5), text }));
  app.exit(linked ? 0 : 1);
});
