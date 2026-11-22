import { DRAFT, README, at } from "../test/projectApi";
import type { DocumentQuestion, ProjectDocument } from "./api";
import { gapSentence, versionGaps } from "./gaps";

function question(n: number): DocumentQuestion {
  return { question_id: `q-${String(n).padStart(16, "0")}`, question_prompt: `Question ${n}?` };
}

/** The README with `kind` and `asked` questions on its version, the first `answered` of them answered. */
function asking(kind: string, asked: number, answered: number): ProjectDocument {
  const questions = Array.from({ length: asked }, (_, i) => question(i));
  const answers = questions.slice(0, answered).map((q) => ({
    question_id: q.question_id,
    answer_text: "Given.",
    answered_at: DRAFT.added_at,
    answered_by: DRAFT.added_by,
    version: DRAFT.version,
  }));
  return { ...README, document_kind: kind, answers, versions: [{ ...DRAFT, document_kind: kind, questions }] };
}

describe("versionGaps", () => {
  it("counts a version's gaps by its questions, and its open questions by the answers recorded", () => {
    const document = asking("readme", 3, 1);
    const gaps = versionGaps(document, at(document.versions, 0));
    expect(gaps).toMatchObject({ gaps: 3, open: 2 });
  });

  it.each([
    ["readme", /gaps/],
    ["data_dictionary", /unknown cells/],
    ["metadata_record", /empty fields/],
    ["dmp", /gaps/],
  ])("names a %s's gaps in its own words", (kind, words) => {
    const document = asking(kind, 2, 0);
    expect(versionGaps(document, at(document.versions, 0)).gapWords).toMatch(words);
  });

  it("says when an answered gap is still in this version, to be placed by the next draft", () => {
    const document = asking("readme", 2, 1);
    expect(gapSentence(versionGaps(document, at(document.versions, 0)), 1)).toMatch(/next draft/);
    const none = asking("readme", 2, 0);
    expect(gapSentence(versionGaps(none, at(none.versions, 0)), 1)).not.toMatch(/next draft/);
  });

  it("says a version with no questions records no gaps", () => {
    const document = asking("readme", 0, 0);
    const gaps = versionGaps(document, at(document.versions, 0));
    expect(gaps).toMatchObject({ gaps: 0, open: 0 });
    expect(gapSentence(gaps, 1)).toMatch(/no gaps/);
  });
});
