import { defineConfig } from "@playwright/test";

// The final check runs against the BUILT app, served on 127.0.0.1:4310.
// One worker: screenshots and the single preview server must not race.
export default defineConfig({
  testDir: "./checks",
  outputDir: "./test-results",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:4310", browserName: "chromium", deviceScaleFactor: 2 },
  webServer: {
    command: "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4310 --strictPort",
    url: "http://127.0.0.1:4310",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
