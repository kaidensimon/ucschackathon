// npm run package:mac
// Builds "GX10 Council.app" for this Mac (Apple silicon) into ../release/.
// The app holds only the Electron shell and the built screens (ui/dist). Unsigned:
// fine on the Mac that built it; another Mac would need it built there or signed.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { packager } from "@electron/packager";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const keep = [/^\/dist($|\/)/, /^\/electron($|\/)/, /^\/package\.json$/];
const paths = await packager({
  dir: ui,
  out: path.resolve(ui, "..", "release"),
  name: "GX10 Council",
  platform: "darwin",
  arch: "arm64",
  overwrite: true,
  prune: false,
  // keep only the shell and the built screens; everything else in ui/ stays out of the app
  ignore: (p) => p !== "" && !keep.some((re) => re.test(p)),
});
console.log(`packaged: ${paths.join(", ")}`);
