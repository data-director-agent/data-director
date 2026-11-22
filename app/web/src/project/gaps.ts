/**
 * What a version leaves for the researcher to supply, counted from what the project log records
 * with it and never from its prose (#1282). Every gap a drafter leaves has exactly one question on
 * the version (`docs/specs/drafting.md`, invariant 5), so a version's gaps are its questions; those
 * no recorded answer has answered are its open questions. An answered gap is still a gap in this
 * version's text: the answer is placed by the next draft.
 */

import type { DocumentQuestion, DocumentVersion, ProjectDocument } from "./api";

/** The questions of `version` that no answer recorded for `document` has answered yet. */
export function openQuestions(document: ProjectDocument, version: DocumentVersion): DocumentQuestion[] {
  const answered = new Set(document.answers.map((a) => a.question_id));
  return version.questions.filter((q) => !answered.has(q.question_id));
}

/** What a gap is called in each kind of document, one and many. */
const GAP_WORDS: Record<string, readonly [string, string]> = {
  readme: ["gap", "gaps"],
  data_dictionary: ["unknown cell", "unknown cells"],
  metadata_record: ["empty field", "empty fields"],
};

export interface VersionGaps {
  /** The version's gaps: placeholders in a README, unknown cells in a dictionary, null fields in a record. */
  gaps: number;
  /** Its questions that no recorded answer has answered. */
  open: number;
  /** The gaps, counted in words, such as "7 gaps" or "1 empty field". */
  gapWords: string;
  /** The open questions, counted in words. */
  openWords: string;
}

function counted(n: number, [one, many]: readonly [string, string]): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function versionGaps(document: ProjectDocument, version: DocumentVersion): VersionGaps {
  const gaps = version.questions.length;
  const open = openQuestions(document, version).length;
  return {
    gaps,
    open,
    gapWords: counted(gaps, GAP_WORDS[version.document_kind] ?? ["gap", "gaps"]),
    openWords: counted(open, ["open question", "open questions"]),
  };
}

/** One sentence saying what `version` leaves open, or that it records nothing open. */
export function gapSentence(gaps: VersionGaps, version: number): string {
  if (gaps.gaps === 0) return `Version ${version} records no gaps and no open questions.`;
  const answered = gaps.gaps - gaps.open;
  const placed =
    answered === 0
      ? ""
      : ` ${answered === 1 ? "One question has" : `${answered} questions have`} been answered; the next draft places ${answered === 1 ? "that answer" : "those answers"}, not this version.`;
  return `Version ${version} has ${gaps.gapWords} and ${gaps.openWords}.${placed}`;
}
