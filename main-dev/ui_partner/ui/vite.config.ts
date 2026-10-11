import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // relative paths, so the built app also opens from files inside the Electron shell
  base: "./",
  plugins: [react(), tailwindcss()],
  // scripts/look.mjs gives each agent's dev server its own cache folder
  cacheDir: process.env.GX10_VITE_CACHE || "node_modules/.vite",
  server: { host: "127.0.0.1" },
  preview: { host: "127.0.0.1", port: 4310, strictPort: true },
});
