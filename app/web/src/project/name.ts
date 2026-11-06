/**
 * What the shell calls a project and a document, shared by the projects list and a project's
 * page so that neither depends on the other.
 */

import type { ProjectDocument, ProjectSummary } from "./api";

const KINDS: Record<string, string> = {
  metadata_record: "Metadata record",
  readme: "README",
  data_dictionary: "Data dictionary",
  dmp: "Data management plan",
};

/** A day as the person's locale writes it, or the timestamp as given if it is not one. */
export function day(at: string): string {
  const date = new Date(at);
  return Number.isNaN(date.getTime()) ? at : date.toLocaleDateString([], { dateStyle: "medium" });
}

/** A project's name: its title, else its first conversation's, else when it was started. */
export function projectName(project: ProjectSummary): string {
  if (project.title) return project.title;
  const first = project.conversations[project.conversations.length - 1];
  return first?.title || `Project started ${day(project.created_at)}`;
}

/** A document's name: its title, else what kind of document it is. */
export function documentName(document: Pick<ProjectDocument, "document_kind" | "document_title">) {
  return document.document_title ?? KINDS[document.document_kind] ?? "Document";
}
