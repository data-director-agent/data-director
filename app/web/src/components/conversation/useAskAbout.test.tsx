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
  const begin = vi.fn();
  const box = { current: document.createElement("textarea") };
  const view = renderHook((read: DocumentsRead) =>
    useAskAboutQuestion(read, { setText: vi.fn(), box, keep: { conversation: null, run: null } }, begin), {
    initialProps: documents,
  });
  return { begin, ...view };
}

describe("useAskAboutQuestion", () => {
  it("starts a new conversation with the question once the documents are read, then drops it from the address", () => {
    const { begin, rerender } = ask(`${README.document_id}/${QUESTION.question_id}`, { state: "loading" });
    expect(begin).not.toHaveBeenCalled();
    rerender(LOADED);
    expect(begin).toHaveBeenCalledTimes(1);
    expect(begin).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: askAboutQuestion("README", QUESTION) }),
    );
    expect(location.search).toBe("");
  });

  it("ignores a question the project's documents do not ask", () => {
    const { begin } = ask(`${README.document_id}/q-nonesuch`, LOADED);
    expect(begin).not.toHaveBeenCalled();
    expect(location.search).toBe("");
  });
});
