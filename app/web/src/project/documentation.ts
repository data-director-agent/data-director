/**
 * Reading the text of a document a researcher attached to a project
 * (`GET /api/projects/{id}/documentation/{digest}`), which answers with text rather than JSON.
 */

import { json } from "../http";

/** An attached document's text and the media type it is read as. */
export interface DocumentationText {
  text: string;
  mediaType: string;
}

/** Where an attached document is; with `?original`, the Word or PDF file it was read from. */
export function documentationPath(projectId: string, digest: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/documentation/${encodeURIComponent(digest)}`;
}

/** The document's text as stored, or with `preview` a copy to read, and its media type. A refusal
 * is raised as for any endpoint (`json`). */
export async function readDocumentationText(
  projectId: string,
  digest: string,
  preview: boolean,
  signal?: AbortSignal,
): Promise<DocumentationText> {
  const path = `${documentationPath(projectId, digest)}${preview ? "?preview" : ""}`;
  const response = await fetch(path, signal ? { signal } : {});
  if (!response.ok) return json<DocumentationText>(response);
  const type = response.headers.get("content-type") ?? "text/plain";
  return { text: await response.text(), mediaType: type.split(";")[0]?.trim() || "text/plain" };
}
