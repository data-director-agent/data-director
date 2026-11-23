import { renderHook } from "@testing-library/react";

import fixture from "../../../fixtures/project-answers.json";
import type { ProjectDocuments } from "../../project/api";
import type { DocumentsRead } from "../../project/drafted";
import { homePath } from "../../route";
import { askAboutQuestion, useAskAboutQuestion } from "./useAskAbout";

// A README whose one question the "Talk this through" link names (app/tests/test_document_answers.py).
const DOCUMENTS = (fixture as ProjectDocuments).documents;
const README = DOCUMENTS[0];
const QUESTION = README?.versions[0]?.questions[0];
if (!README || !QUESTION) throw new Error("the fixture has no question");
const LOADED: DocumentsRead = { state: "loaded", documents: DOCUMENTS };

function ask(question: string, documents: DocumentsRead) {
  history.replaceState(null, "", homePath({ question }));
  const setText = vi.fn();
  const box = { current: document.createElement("textarea") };
  const view = renderHook((read: DocumentsRead) =>
    useAskAboutQuestion(read, { setText, box, keep: { conversation: null, run: null } }), {
    initialProps: documents,
  });
  return { setText, ...view };
}

describe("useAskAboutQuestion", () => {
  it("puts the question in the message box once the documents are read, then drops it from the address", () => {
    const { setText, rerender } = ask(`${README.document_id}/${QUESTION.question_id}`, { state: "loading" });
    expect(setText).not.toHaveBeenCalled();
    rerender(LOADED);
    expect(setText).toHaveBeenCalledTimes(1);
    expect(setText).toHaveBeenCalledWith(askAboutQuestion("README", QUESTION));
    expect(setText.mock.calls[0]?.[0]).toContain(QUESTION.question_prompt);
    expect(location.search).toBe("");
  });

  it("ignores a question the project's documents do not ask", () => {
    const { setText } = ask(`${README.document_id}/q-nonesuch`, LOADED);
    expect(setText).not.toHaveBeenCalled();
    expect(location.search).toBe("");
  });
});
