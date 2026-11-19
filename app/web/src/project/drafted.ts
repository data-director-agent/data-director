/**
 * Which of a project's document versions a run drafted, read from what the project log records:
 * each drafted version names the invocation that drafted it (`drafted_by.invocation_id`). The
 * shell matches on that alone, so it names no agent and infers nothing from a run's payload: a
 * payload that never became a project document has no version here (docs/specs/app.md).
 */

import type { DocumentVersion, ProjectDocument } from "./api";

/** A version drafted by one of the runs asked about, beside its document's latest version. */
export interface DraftedVersion {
  document: ProjectDocument;
  version: DocumentVersion;
  latest: DocumentVersion;
}

/** A project's documents as the workspace last read them, for the transcript and the side bar. */
export type DocumentsRead =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; documents: ProjectDocument[] };

/** The document's latest version, or undefined when it has none. */
export function latestOf(document: ProjectDocument): DocumentVersion | undefined {
  return document.versions[document.versions.length - 1];
}

/** The versions drafted by any of `invocationIds`, in the order the project lists them. */
export function draftedBy(
  invocationIds: readonly string[],
  documents: readonly ProjectDocument[],
): DraftedVersion[] {
  const ids = new Set(invocationIds);
  return documents.flatMap((document) => {
    const latest = latestOf(document);
    if (!latest) return [];
    return document.versions
      .filter((version) => version.drafted_by && ids.has(version.drafted_by.invocation_id))
      .map((version) => ({ document, version, latest }));
  });
}

/** Where a document is reviewed: open in the reader on the project's documents page. */
export function documentHref(projectId: string, documentId: string): string {
  return `/projects/${encodeURIComponent(projectId)}?doc=${encodeURIComponent(documentId)}`;
}
