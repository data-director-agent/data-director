import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/project-answers.json";
import {
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocument,
  type ProjectDocuments,
  httpProjectApi,
} from "../../project/api";
import { DocumentCard } from "./DocumentCard";

// A README whose one question has been answered (app/tests/test_document_answers.py), its version
// made a note that asks first (docs/specs/drafting.md).
const ANSWERED = fixture as ProjectDocuments;
const README = ANSWERED.documents[0];
const VERSION = README?.versions[0];
const QUESTION = VERSION?.questions[0];
const SAVED = README?.answers[0];
if (!README || !VERSION || !QUESTION || !SAVED) throw new Error("the fixture has no answered README");

function renderCard(
  document: ProjectDocument,
  { answer = vi.fn(), onWrite }: { answer?: ProjectApi["answer"]; onWrite?: (message: string) => void } = {},
) {
  const version = document.versions[0];
  if (!version) throw new Error("no version");
  const onAnswered = vi.fn();
  const view = render(
    <ProjectApiContext.Provider value={{ ...httpProjectApi, answer }}>
      <ul>
        <DocumentCard
          projectId={ANSWERED.project_id}
          drafted={{ document, version, latest: version }}
          idPrefix="card"
          answering={{ maxLength: ANSWERED.answer_max_length, onAnswered }}
          {...(onWrite ? { onWrite } : {})}
        />
      </ul>
    </ProjectApiContext.Provider>,
  );
  return { onAnswered, ...view };
}

describe("DocumentCard", () => {
  it("shows a version that asks first with no preview and a way to write the README", () => {
    const asking = { ...VERSION, stage: "questions" as const };
    renderCard({ ...README, versions: [asking] }, { onWrite: vi.fn() });
    expect(screen.getByText("Questions first")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Preview/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Write the README" })).toBeVisible();
  });

  it("shows the answers saved when it is drawn afresh, as after a reload", async () => {
    // Drawn from the documents the server reads back from the project log, with no state kept.
    const { container } = renderCard(README);
    const change = screen.getByRole("button", { name: `Change your answer to: ${QUESTION.question_prompt}` });
    expect(change).toBeVisible();
    const item = change.closest("li");
    if (!item) throw new Error("the answer is not in a list");
    expect(within(item).getByText(SAVED.answer_text)).toBeVisible();
    expect(within(item).getByText(QUESTION.question_prompt)).toBeVisible();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("puts a saved answer back in the form to change it, and records the new answer", async () => {
    const answer = vi.fn<ProjectApi["answer"]>().mockResolvedValue(ANSWERED);
    const { onAnswered } = renderCard(README, { answer });
    await userEvent.click(
      screen.getByRole("button", { name: `Change your answer to: ${QUESTION.question_prompt}` }),
    );
    const box = screen.getByRole("textbox", { name: QUESTION.question_prompt });
    expect(box).toHaveValue(SAVED.answer_text);
    expect(box).not.toHaveAccessibleDescription(/Not saved yet/);

    await userEvent.type(box, " and peat");
    expect(box).toHaveAccessibleDescription(/Not saved yet/);
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(answer).toHaveBeenCalledWith(ANSWERED.project_id, README.document_id, VERSION.version, [
      { answered_question: QUESTION.question_id, answer_text: `${SAVED.answer_text} and peat` },
    ]);
    expect(onAnswered).toHaveBeenCalledWith(ANSWERED);
  });

  it("keeps the saved answer when a change is given up", async () => {
    renderCard(README);
    await userEvent.click(
      screen.getByRole("button", { name: `Change your answer to: ${QUESTION.question_prompt}` }),
    );
    await userEvent.type(screen.getByRole("textbox", { name: QUESTION.question_prompt }), " and peat");
    await userEvent.click(screen.getByRole("button", { name: /Keep the saved answer/ }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText(SAVED.answer_text)).toBeVisible();
  });
});
