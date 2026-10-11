// npm run look -- --port 5311 --route "#/chat/lease?scene=debating" --agent table
//   [--name stem] [--theme light|dark|both] [--width 1440] [--height 830] [--scale 2]
//   [--grey] [--full] [--browser webkit] [--press Key] [--click selector] [--reduced-motion]
// Starts this agent's own dev server on its port, looks, and stops the server.
// Refuses a busy port. Screenshots go to ui/.looks/<agent>/.
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { commonOptions, look, parseArgs, printReport } from "./lib/look-core.mjs";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));
const port = Number(args.port);
const ALLOWED = [5311, 5312, 5313, 5314];
if (!ALLOWED.includes(port)) {
  console.error(`look needs --port, one of ${ALLOWED.join(", ")}`);
  process.exit(2);
}
const agent = String(args.agent || `port-${port}`).replace(/[^a-z0-9-]/gi, "-");

const portOpen = () =>
  new Promise((resolve) => {
    const s = net.connect({ host: "127.0.0.1", port });
    s.once("connect", () => {
      s.destroy();
      resolve(true);
    });
    s.once("error", () => resolve(false));
  });

if (await portOpen()) {
  console.error(`Port ${port} is busy. look does not reuse or stop a server it did not start. Report this.`);
  process.exit(3);
}

const server = spawn(
  process.execPath,
  [
    path.join(ui, "node_modules/vite/bin/vite.js"),
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
    "--strictPort",
    "--logLevel",
    "warn",
  ],
  // one cache folder per port, so parallel agents do not share one (read in vite.config.ts)
  { cwd: ui, stdio: ["ignore", "ignore", "pipe"], env: { ...process.env, GX10_VITE_CACHE: `.vite-${port}` } },
);
let serverErr = "";
server.stderr.on("data", (d) => {
  serverErr += d;
});
const stop = () =>
  new Promise((resolve) => {
    if (server.exitCode !== null) return resolve();
    server.once("exit", resolve);
    server.kill("SIGTERM");
    setTimeout(() => server.kill("SIGKILL"), 3000).unref();
  });
process.on("SIGINT", () => stop().then(() => process.exit(130)));
process.on("SIGTERM", () => stop().then(() => process.exit(143)));

let code = 1;
try {
  const deadline = Date.now() + 30000;
  while (!(await portOpen())) {
    if (server.exitCode !== null) throw new Error(`dev server exited early: ${serverErr.slice(0, 400)}`);
    if (Date.now() > deadline) throw new Error("dev server not ready after 30 s");
    await new Promise((r) => setTimeout(r, 150));
  }
  const origin = `http://127.0.0.1:${port}`;
  const route = typeof args.route === "string" ? args.route : "";
  const opts = commonOptions(args, {
    outDir: path.join(ui, ".looks", agent),
    name: (route.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "home").slice(0, 60),
  });
  const report = await look({ ...opts, url: `${origin}/${route}`, allow: origin });
  code = printReport(report);
} catch (e) {
  console.error(`look failed: ${e.message}`);
  code = 1;
} finally {
  await stop();
}
const stillOpen = await portOpen();
console.log(`PORT ${port} ${stillOpen ? "STILL BUSY (report this)" : "free"}`);
process.exit(stillOpen ? 4 : code);
