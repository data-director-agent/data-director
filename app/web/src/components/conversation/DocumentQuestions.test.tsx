import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/project-answers.json";
import {
  DecisionConflict,
  type DocumentQuestion,
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocument,
  type ProjectDocuments,
  httpProjectApi,
} from "../../project/api";
import { DocumentQuestions, QUESTIONS_AT_ONCE } from "./DocumentQuestions";

// What the server says after an answer (app/tests/test_document_answers.py): a README whose one
// question has been answered.
const ANSWERED = fixture as ProjectDocuments;
function first<T>(items: T[]): T {
  const item = items[0];
  if (item === undefined) throw new Error("the fixture has none");
  return item;
}

const README = first(ANSWERED.documents);
const VERSION = first(README.versions);

/** A data dictionary cell's question, as the Documentation Editor asks it. */
function cell(n: number): DocumentQuestion {
  return {
    question_id: `q-${n.toString(16).padStart(16, "0")}`,
    question_prompt: `What unit is field_${n} in?`,
    gap_file: "data/soil.csv",
    gap_field: `field_${n}`,
    gap_column: "unit",
  };
}

const ASKING = QUESTIONS_AT_ONCE + 2;
const UNANSWERED: ProjectDocument = {
  ...README,
  answers: [],
  versions: [{ ...VERSION, questions: Array.from({ length: ASKING }, (_, n) => cell(n + 1)) }],
};

function renderQuestions(document: ProjectDocument, answer: ProjectApi["answer"]) {
  const onAnswered = vi.fn();
  const api: ProjectApi = { ...httpProjectApi, answer };
  const view = render(
    <ProjectApiContext.Provider value={api}>
      <DocumentQuestions
        projectId={ANSWERED.project_id}
        document={document}
        version={first(document.versions)}
        name="README"
        onAnswered={onAnswered}
      />
    </ProjectApiContext.Provider>,
  );
  return { onAnswered, ...view };
}

describe("DocumentQuestions", () => {
  it("puts a few questions at a time, each labelled and described by what it fills", async () => {
    const { container } = renderQuestions(UNANSWERED, vi.fn());
    expect(screen.getByRole("group", { name: new RegExp(`${ASKING} questions`) })).toBeVisible();
    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(QUESTIONS_AT_ONCE);
    expect(screen.getByRole("textbox", { name: "What unit is field_1 in?" })).toHaveAccessibleDescription(
      /data\/soil\.csv › field_1 › unit/,
    );
    expect(screen.getByRole("button", { name: "Save answers" })).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: /Show other questions/ }));
    expect(screen.getAllByRole("textbox")).toHaveLength(ASKING - QUESTIONS_AT_ONCE);
    expect(screen.getByRole("textbox", { name: `What unit is field_${ASKING} in?` })).toBeVisible();
  });

  it("sends only the answers given, for the version asked, and hands back what the server read", async () => {
    const answer = vi.fn<ProjectApi["answer"]>().mockResolvedValue(ANSWERED);
    const { onAnswered } = renderQuestions(UNANSWERED, answer);
    await userEvent.type(screen.getByRole("textbox", { name: "What unit is field_2 in?" }), " mg/kg ");
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(answer).toHaveBeenCalledWith(ANSWERED.project_id, README.document_id, VERSION.version, [
      { answered_question: cell(2).question_id, answer_text: "mg/kg" },
    ]);
    expect(onAnswered).toHaveBeenCalledWith(ANSWERED);
    expect(screen.getByRole("status")).toHaveTextContent(/Recorded 1 answer/);
  });

  it("asks nothing once every question is answered", () => {
    renderQuestions(README, vi.fn());
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("says the answers were not recorded when the document has moved on", async () => {
    const answer = vi.fn<ProjectApi["answer"]>().mockRejectedValue(
      new DecisionConflict({
        type: "https://example.org/version-not-latest",
        title: "The document has moved on",
        detail: "Version 1 is not the latest.",
      }),
    );
    const { onAnswered } = renderQuestions(UNANSWERED, answer);
    await userEvent.type(screen.getByRole("textbox", { name: "What unit is field_1 in?" }), "m");
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/not recorded: Version 1 is not the latest/);
    expect(onAnswered).not.toHaveBeenCalled();
  });
});
