// The names a seat goes by on screen.
//   seatLabel    = the short name drawn on the figure and shown in lists ("DeepSeek", "GPT-OSS")
//   seatFullName = the whole model name, for tooltips and the chat view ("GPT-OSS 20B (OpenAI, local)")
// Both come from the model's own name, so a seat never shows a name cut in the middle of a word.
import { makerOf } from "./makers";

interface Named {
  shortName: string;
  modelName: string;
}

/** the longest name a figure carries */
const LABEL_MAX = 9;

/** The council's models, as the backend names them (lower case), and the name each is drawn with. */
const KNOWN: Record<string, string> = {
  "gpt-oss 20b": "GPT-OSS",
  "deepseek r1 14b": "DeepSeek",
  "qwen3 14b": "Qwen3",
  "qwen3.5 9b": "Qwen3.5",
  "phi-4 14b": "Phi-4",
  "gemma 4 12b": "Gemma 4",
  "granite 4.1 8b": "Granite",
  "falcon3 10b": "Falcon3",
};

/** a model's size as it is written in a name: "14B", "20b", "3.8B", "560M" */
const SIZE = /(^|[\s\-_:])\d+(\.\d+)?[bm](?![a-z0-9])/i;

/** the file's own name, without folders or a file ending */
function ownName(name: string): string {
  return (name.split(/[\\/]/).pop() ?? "").replace(/\.(gguf|bin|safetensors)$/i, "").trim();
}

/** "gpt" is an abbreviation: always upper case, with "-oss" when it follows */
function upperGpt(name: string): string {
  return name.replace(/(^|[^a-z0-9])gpt(-oss)?(?![a-z])/gi, (found) => found.toUpperCase());
}

/** As many whole words from the start as fit in `LABEL_MAX` characters; the first word is never cut. */
function wholeWords(name: string): string {
  let out = "";
  for (const piece of name.match(/[^\s\-_:]+[\s\-_:]*/g) ?? []) {
    const next = (out + piece).replace(/[\s\-_:]+$/, "");
    if (out !== "" && next.length > LABEL_MAX) break;
    out += piece;
  }
  return out.replace(/[\s\-_:]+$/, "");
}

/** The name drawn on a seat and shown in lists. */
export function seatLabel(seat: Named): string {
  const model = ownName(seat.modelName);
  const known = KNOWN[model.toLowerCase().replace(/\s+/g, " ")];
  if (known !== undefined) return known;
  // a model name that states its size: the family is what comes before the size
  const size = SIZE.exec(model);
  const family = size ? model.slice(0, size.index).trim() : "";
  const label = wholeWords(upperGpt(family !== "" ? family : seat.shortName.trim()));
  return label !== "" ? label : seat.shortName;
}

/** The whole model name with its maker, for tooltips and the chat view. Every model runs on the box. */
export function seatFullName(seat: Named): string {
  const model = upperGpt(ownName(seat.modelName)) || seatLabel(seat);
  const maker = makerOf(seat);
  return maker ? `${model} (${maker.company}, local)` : `${model} (local)`;
}
