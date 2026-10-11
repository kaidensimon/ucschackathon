// Hands the owner a file through the browser's own download: the words are put in a Blob
// and a link to it is pressed. Nothing is sent anywhere.
import type { ExportedChat } from "../../engine/client";

/** A chat's title can hold marks a file name cannot. */
export function safeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]+/g, "-").trim() || "chat";
}

/** Starts the download and answers with the file name it used. */
export function saveFile(file: ExportedChat): string {
  const filename = safeFilename(file.filename);
  const url = URL.createObjectURL(new Blob([file.text], { type: `${file.mime};charset=utf-8` }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  // the download has its own hold on the words by the next turn; the address can go
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return filename;
}
