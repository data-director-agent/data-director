/**
 * Who a question's suggested answer comes from, in words (docs/specs/drafting.md, invariant 7):
 * a model, the researcher's own answer to another document's question or a decision people in
 * the project made (`suggestion_derivation` `answer`, #1284), or the institution's own list of
 * storage services, from the deployment's profile (`suggested_from` `institution`). Either way it
 * is only offered, and recorded only once a person saves or accepts it.
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

/** Whether the suggestion was made by a model, rather than copied or taken from a list. */
export function byAModel(q: DocumentQuestion): boolean {
  return !fromAPerson(q) && q.suggested_from !== "institution";
}

/** Where the suggestion came from, completing "Suggested from …" or "Suggested by …". */
export function suggestionSource(q: DocumentQuestion): string {
  if (q.suggested_from === "institution") return "from your institution's own list";
  if (!fromAPerson(q)) return "by a model";
  if (q.suggested_from === "decision") return "from what was decided in the project";
  return `from your answer for ${DOCUMENT_NAMES[q.suggested_from ?? ""] ?? "another document"}`;
}
