/**
 * A supporting document the researcher attaches to a message (docs/specs/app.md), such as a
 * protocol, a codebook or an existing README. It is read here, as text, only to check that it is
 * one the project keeps and to show it before it is attached; the server checks it again and the
 * conversation's project keeps it (docs/specs/projects.md). Its text never goes into the message,
 * and agents are told only its name, size and type.
 *
 * Before it is attached, the server checks its text for possible personal data and secrets
 * (`checkDocument`, #473). What is found is named by kind, never quoted, and the turn must say the
 * researcher confirmed each kind, or the server holds the document back.
 */

import { json } from "../http";

/** The media types a project keeps as documentation, by the file extensions that name them. */
const MEDIA_TYPES: Record<string, string> = {
  ".md": "text/markdown",
  ".markdown": "text/markdown",
  ".txt": "text/plain",
};

/** The extensions the file picker offers for a document. */
export const DOCUMENT_EXTENSIONS = Object.keys(MEDIA_TYPES);

/** The largest document a project keeps, in bytes of UTF-8 (`DOCUMENTATION_MAX_BYTES`). */
export const DOCUMENT_MAX_BYTES = 256 * 1024;

/** The user guide's page on attaching a document. */
export const DOCUMENT_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/attaching-a-document/";

/** A document read from a file, as the turn's `documentation` sends it. */
export interface AttachedDocument {
  name: string;
  media_type: string;
  text: string;
  /** The size of its text in bytes of UTF-8. */
  size: number;
  /** The kinds of possible personal data or secrets the researcher confirmed it holds. */
  confirmed?: string[];
}

/** One kind of thing the check found: never a value, a line or where in the text. */
export interface DocumentFinding {
  /** A kind of personal data, such as `email address`, or `secret`. */
  kind: string;
  /** For a secret, its type, such as `AWS Access Key`. */
  detail?: string;
  /** How many places, as a band: `1`, `2 to 4` or `5 or more`. */
  places: string;
  confidence: "low" | "medium" | "high";
}

/** What `POST /api/documentation/check` answers. */
export interface DocumentCheck {
  findings: DocumentFinding[];
  /** The kinds to confirm: a secret's type stands for itself. */
  kinds: string[];
  /** What the check ran, to say alongside what it found. */
  checked_with: string;
}

/** What the server finds in `document`'s text; nothing is kept. */
export async function checkDocument(
  document: AttachedDocument,
  signal?: AbortSignal,
): Promise<DocumentCheck> {
  const response = await fetch("/api/documentation/check", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({
      name: document.name,
      media_type: document.media_type,
      text: document.text,
    }),
    ...(signal ? { signal } : {}),
  });
  return json<DocumentCheck>(response);
}

/** One finding in words, never repeating what was found. */
export function findingWords(finding: DocumentFinding): string {
  const what = finding.kind === "secret" ? `A secret: ${finding.detail ?? "of some kind"}` : finding.kind;
  const where = finding.places === "1" ? "in 1 place" : `in ${finding.places} places`;
  return `${what[0]?.toUpperCase() ?? ""}${what.slice(1)}, ${where} (${finding.confidence} confidence)`;
}

/** What the conductor told a turn's agent of a document (`Message.project_documentation`). */
export interface DocumentationSummary {
  documentation_name: string;
  documentation_digest: string;
  documentation_media_type: string;
  documentation_size: number;
  documentation_added_at: string;
}

/** Why a file is not a document the project would keep. */
export class NotADocument extends Error {}

/** The media type of a file named `name`, or null if a project keeps no document of its kind. */
export function documentMediaType(name: string): string | null {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? null : (MEDIA_TYPES[name.slice(dot).toLowerCase()] ?? null);
}

/** Whether a file named `name` is read as a document rather than as an inventory. */
export function isDocumentName(name: string): boolean {
  return documentMediaType(name) !== null;
}

/** A size in bytes, as a person reads it. */
export function describeSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
}

/** `text` read from the file `name` as a document, or `NotADocument` saying why it is not one. */
export function readDocument(text: string, name: string): AttachedDocument {
  const mediaType = documentMediaType(name);
  if (mediaType === null) {
    throw new NotADocument(
      `${name} is not a document Data Director keeps. Attach a plain text (.txt) or Markdown ` +
        "(.md) file, or an inventory (.json).",
    );
  }
  if (!text.trim()) throw new NotADocument(`${name} is empty.`);
  const size = new TextEncoder().encode(text).length;
  if (size > DOCUMENT_MAX_BYTES) {
    throw new NotADocument(
      `${name} is ${describeSize(size)}; a document may be at most ` +
        `${describeSize(DOCUMENT_MAX_BYTES)}. Data files are never attached: describe them with ` +
        "an inventory instead.",
    );
  }
  return { name, media_type: mediaType, text, size };
}
