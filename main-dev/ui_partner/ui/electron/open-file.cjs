// Opens one local HTML file (the look chooser, a study) in an Electron window.
// Usage: electron ui/electron/open-file.cjs "/absolute/path/to/file.html"
// Same rule as the app: only local files load; nothing goes to the internet.
const { app, BrowserWindow, session } = require("electron");
const path = require("node:path");

const file = process.argv.slice(2).find((a) => a.endsWith(".html"));
app.setName("GX10 Council: choose a look");

app.whenReady().then(() => {
  if (!file) {
    console.error("open-file needs the path of an .html file");
    app.quit();
    return;
  }
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const ok = details.url.startsWith("file:") || details.url.startsWith("data:") || details.url.startsWith("devtools:");
    callback({ cancel: !ok });
  });
  const win = new BrowserWindow({
    width: 1500,
    height: 950,
    title: "GX10 Council: choose a look",
    backgroundColor: "#FFFFFF",
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.loadFile(path.resolve(file));
});

app.on("window-all-closed", () => app.quit());
