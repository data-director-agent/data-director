/**
 * What the shell needs to know about a document's media type: its essence, the file name to
 * download it under, and how a preview reads it.
 */

const EXTENSIONS: Record<string, string> = {
  "text/markdown": "md",
  "text/csv": "csv",
  "application/json": "json",
  "application/ld+json": "jsonld",
  "application/xml": "xml",
  "text/xml": "xml",
  "text/plain": "txt",
};

/** The media type without its parameters, such as `text/markdown` for `text/markdown; charset=utf-8`. */
export function essence(mediaType: string): string {
  return (mediaType.split(";")[0] ?? "").trim().toLowerCase();
}

/** A file name for the download: the document's title in lower case, hyphenated. */
export function fileName(title: string, mediaType: string): string {
  const stem =
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "document";
  return `${stem}.${EXTENSIONS[essence(mediaType)] ?? "txt"}`;
}

/** The text as a `data:` URL, so that a link can offer it as a download. */
export function dataUrl(mediaType: string, text: string): string {
  return `data:${essence(mediaType) || "text/plain"};charset=utf-8,${encodeURIComponent(text)}`;
}

/** How a preview reads a media type; `source` shows the text as it is. */
export type Reading = "markdown" | "csv" | "json" | "source";

export function readingOf(mediaType: string): Reading {
  const type = essence(mediaType);
  if (type === "text/markdown") return "markdown";
  if (type === "text/csv") return "csv";
  if (type === "application/json" || type.endsWith("+json")) return "json";
  return "source";
}
