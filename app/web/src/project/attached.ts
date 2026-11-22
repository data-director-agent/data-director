/**
 * What the shell says of a document a researcher attached to a project: what kind of file it came
 * as, and a line describing it for the Documents list.
 */

import type { DocumentationSummary } from "../conversation/documentation";
import { describeSize } from "../conversation/documentation";
import { formatDateTime } from "../format";
import { essence } from "./media";

/** The kind of file an attached document came as. */
export type AttachedKind = "word" | "pdf" | "markdown" | "text";

const LABELS: Record<AttachedKind, string> = {
  word: "Word document",
  pdf: "PDF",
  markdown: "Markdown",
  text: "Plain text",
};

/** The kind of file `document` was attached as: the original's, for one read from a file. */
export function attachedKind(document: DocumentationSummary): AttachedKind {
  const source = essence(document.documentation_source_media_type ?? "");
  if (source === "application/pdf") return "pdf";
  if (source.includes("wordprocessingml")) return "word";
  return essence(document.documentation_media_type) === "text/markdown" ? "markdown" : "text";
}

/** The kind of file, in words. */
export function attachedKindLabel(document: DocumentationSummary): string {
  return LABELS[attachedKind(document)];
}

/** The day it was attached, as a person reads it. */
export function attachedOn(document: DocumentationSummary): string {
  return formatDateTime(document.documentation_added_at, { dateStyle: "medium" });
}

/** A line for the list: its kind, its size (of the text read, for one read from a file) and the
 * day it was attached. */
export function attachedDetail(document: DocumentationSummary): string {
  const size = describeSize(document.documentation_size);
  const read = document.documentation_source_media_type ? `${size} of text` : size;
  return `${attachedKindLabel(document)} · ${read} · added ${attachedOn(document)}`;
}

/** The project's attached document with `digest`, if it holds one. */
export function findAttached(
  documents: readonly DocumentationSummary[],
  digest: string | null,
): DocumentationSummary | undefined {
  return digest === null ? undefined : documents.find((d) => d.documentation_digest === digest);
}
