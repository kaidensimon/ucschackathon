// npm run slice -- src/components/table
// Type-checks the project and runs only the tests under the given path(s).
// Fails if the path matched no tests, so "nothing ran" never looks like a pass.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = process.argv.slice(2);
if (!targets.length) {
  console.error("Usage: npm run slice -- <path> [more paths]");
  process.exit(2);
}
const run = (bin, args) =>
  spawnSync(process.execPath, [path.join(ui, "node_modules", bin), ...args], { cwd: ui, stdio: "inherit" }).status ?? 1;
const tsc = run("typescript/bin/tsc", ["--noEmit"]);
const tests = run("vitest/vitest.mjs", ["run", ...targets, "--passWithNoTests=false"]);
console.log(`SLICE typecheck exit ${tsc}, tests exit ${tests}`);
process.exit(tsc || tests ? 1 : 0);
