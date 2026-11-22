/**
 * Who a question's suggested answer comes from, in words (docs/specs/drafting.md, invariant 7):
 * a model, or the researcher's own answer to another document's question or a decision people in
 * the project made (`suggestion_derivation` `answer`, #1284). Either way it is only offered,
 * and recorded only once a person saves or accepts it.
 */

import type { DocumentQuestion } from "../api/contract";

const DOCUMENT_NAMES: Record<string, string> = {
  metadata_record: "the metadata record",
  readme: "the README",
  data_dictionary: "the data dictionary",
  dmp: "the data management plan",
  other: "another document",
};

/** Whether the suggestion copies a person's own words rather than a model's. */
export function fromAPerson(q: DocumentQuestion): boolean {
  return q.suggestion_derivation === "answer";
}

/** Where the suggestion came from, completing "Suggested from …" or "Suggested by …". */
export function suggestionSource(q: DocumentQuestion): string {
  if (!fromAPerson(q)) return "by a model";
  if (q.suggested_from === "decision") return "from what was decided in the project";
  return `from your answer for ${DOCUMENT_NAMES[q.suggested_from ?? ""] ?? "another document"}`;
}
