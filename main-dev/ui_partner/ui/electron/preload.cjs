// Runs before the page, in an isolated world. Phase 1 exposes one fact only:
// that the app is running inside the desktop shell. Later phases add the bridge
// to the GX10 gateway and to watched folders here, one named function at a time.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("gx10", {
  shell: "electron",
  platform: process.platform,
  // "Web search" switch: one plain search by the desktop shell; resolves to at most five
  // { title, url, snippet } read off the results page. Nothing else on the machine is reachable.
  webSearch: (question) => ipcRenderer.invoke("gx10:web-search", String(question)),
});
