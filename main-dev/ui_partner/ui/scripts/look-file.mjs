// npm run look:file -- <file.html> [--out dir] [--name stem] [--theme light|dark|both]
//   [--width 1440] [--height 830] [--scale 2] [--grey] [--full] [--browser webkit]
//   [--press Key] [--click selector] [--reduced-motion]
// Opens one static file with every outside request blocked. Exit 1 on a console
// error or an attempted outside request.
import { existsSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { commonOptions, look, parseArgs, printReport } from "./lib/look-core.mjs";

const args = parseArgs(process.argv.slice(2));
const file = args._[0];
if (!file || !existsSync(file)) {
  console.error("look:file needs an existing file. Usage: npm run look:file -- path/to/file.html");
  process.exit(2);
}
const abs = path.resolve(file);
const opts = commonOptions(args, {
  outDir: path.join(path.dirname(abs), "shots"),
  name: path.basename(abs).replace(/\.html?$/, ""),
});
const hash = args.hash ? `#${args.hash}` : "";
const report = await look({ ...opts, url: pathToFileURL(abs).href + hash, allow: "file" });
process.exit(printReport(report));
