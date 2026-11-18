/**
 * A supporting document the researcher attaches to a message (docs/specs/app.md), such as a
 * protocol, a codebook or an existing README. A text or Markdown file is read here, as text, only
 * to check that it is one the project keeps and to show it before it is attached; the server
 * checks it again and the conversation's project keeps it (docs/specs/projects.md). A Word
 * document or PDF is sent to the server to be read inside the deployment (`readSource`), and its
 * text is shown the same way; once attached, the project keeps the file beside the text (#961).
 * Its text never goes into the message.
 */

import { RunRefused, json } from "../http";

/** The media types a project keeps as documentation, by the file extensions that name them. */
const MEDIA_TYPES: Record<string, string> = {
  ".md": "text/markdown",
  ".markdown": "text/markdown",
  ".txt": "text/plain",
};

/** The Word and PDF files a project keeps beside the text read from them, by extension. */
const SOURCE_TYPES: Record<string, string> = {
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".pdf": "application/pdf",
};

/** The extensions the file picker offers for a document. */
export const DOCUMENT_EXTENSIONS = [...Object.keys(MEDIA_TYPES), ...Object.keys(SOURCE_TYPES)];

/** The media types the file picker offers for a document. */
export const DOCUMENT_MEDIA_TYPES = [
  ...new Set([...Object.values(MEDIA_TYPES), ...Object.values(SOURCE_TYPES)]),
];

/** The largest Word or PDF file a project keeps, in bytes (`SOURCE_MAX_BYTES`). */
export const SOURCE_MAX_BYTES = 1024 * 1024;

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
  /** For a Word document or PDF, the file as base64: the turn sends it, not the text. */
  data?: string;
}

/** What the conductor told a turn's agent of a document (`Message.project_documentation`). */
export interface DocumentationSummary {
  documentation_name: string;
  documentation_digest: string;
  documentation_media_type: string;
  documentation_size: number;
  documentation_added_at: string;
  /** The Word or PDF file's media type, for a document whose text was read from one. */
  documentation_source_media_type?: string;
}

/** Why a file is not a document the project would keep. */
export class NotADocument extends Error {}

/** The media type of a file named `name`, or null if a project keeps no document of its kind. */
export function documentMediaType(name: string): string | null {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? null : (MEDIA_TYPES[name.slice(dot).toLowerCase()] ?? null);
}

/** The media type of a Word or PDF file named `name`, or null if it is not one. */
export function sourceMediaType(name: string): string | null {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? null : (SOURCE_TYPES[name.slice(dot).toLowerCase()] ?? null);
}

/** Whether a file named `name` is read as a document rather than as an inventory. */
export function isDocumentName(name: string): boolean {
  return documentMediaType(name) !== null || sourceMediaType(name) !== null;
}

/** A size in bytes, as a person reads it. */
export function describeSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
}

/** `text` read from the file `name` as a document, or `NotADocument` saying why it is not one. */
export function readDocument(text: string, name: string): AttachedDocument {
  const mediaType = documentMediaType(name);
  if (mediaType === null) {
    throw new NotADocument(
      `${name} is not a document Data Director keeps. Attach a plain text (.txt), Markdown ` +
        "(.md), Word (.docx) or PDF (.pdf) file, or an inventory (.json).",
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

/**
 * The Word or PDF `file` with the text the server reads from it, to be checked before it is
 * attached, or `NotADocument` saying why it is not one the project would keep. The file is
 * refused here if it is over `SOURCE_MAX_BYTES`, and the server refuses one it cannot read, such
 * as a scanned PDF with no text layer; it keeps nothing until the turn attaches it.
 */
export async function readSource(file: File): Promise<AttachedDocument> {
  const mediaType = sourceMediaType(file.name);
  if (mediaType === null) return readDocument(await file.text(), file.name);
  if (file.size > SOURCE_MAX_BYTES) {
    throw new NotADocument(
      `${file.name} is ${describeSize(file.size)}; a Word document or PDF may be at most ` +
        `${describeSize(SOURCE_MAX_BYTES)}.`,
    );
  }
  const data = toBase64(new Uint8Array(await file.arrayBuffer()));
  try {
    const read = await json<{ text: string; size: number }>(
      await fetch("/api/documentation/extract", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: file.name, media_type: mediaType, data }),
      }),
    );
    return { name: file.name, media_type: mediaType, text: read.text, size: read.size, data };
  } catch (e) {
    if (e instanceof RunRefused) throw new NotADocument(`${file.name}: ${e.message}`);
    throw e;
  }
}

/** `bytes` as base64, a chunk at a time so that a large file does not overflow the stack. */
function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}
