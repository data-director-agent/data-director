/**
 * A supporting document the researcher attaches to a message (docs/specs/app.md), such as a
 * protocol, a codebook or an existing README. It is read here, as text, only to check that it is
 * one the project keeps and to show it before it is attached; the server checks it again and the
 * conversation's project keeps it (docs/specs/projects.md). Its text never goes into the message,
 * and agents are told only its name, size and type.
 */

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
