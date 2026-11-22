import { render, screen, within } from "@testing-library/react";
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

function renderQuestions(
  document: ProjectDocument,
  answer: ProjectApi["answer"],
  onWrite?: (message: string) => void,
) {
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
        {...(onWrite ? { onWrite } : {})}
      />
    </ProjectApiContext.Provider>,
  );
  return { onAnswered, ...view };
}

describe("DocumentQuestions", () => {
  it("puts a few questions at a time, each labelled and described by what it fills", async () => {
    const { container } = renderQuestions(UNANSWERED, vi.fn());
    expect(screen.getByRole("form", { name: new RegExp(`${ASKING} questions for you`) })).toBeVisible();
    expect(screen.getByRole("group", { name: "Only you can answer these" })).toBeVisible();
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

  it("keeps the parts of one README section on the same page", async () => {
    const parts = ["Title", "Principal investigator", "Contact", "Funding"].map(
      (part, n): DocumentQuestion => ({
        question_id: `q-${(100 + n).toString(16).padStart(16, "0")}`,
        question_prompt: `For the README's General information section, ${part.toLowerCase()}?`,
        gap_section: "General information",
        gap_part: part,
      }),
    );
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [{ ...VERSION, questions: [...parts, cell(1)] }],
    };
    renderQuestions(document, vi.fn());
    expect(screen.getAllByRole("textbox")).toHaveLength(parts.length);
    expect(
      screen.getByRole("textbox", { name: /General information section, funding/ }),
    ).toHaveAccessibleDescription(/General information” › Funding/);

    await userEvent.click(screen.getByRole("button", { name: /Show other questions/ }));
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
  });

  it("says how many files a question about a shared column fills", () => {
    const shared: DocumentQuestion = {
      ...cell(1),
      gap_file: "run_1/forces.csv",
      gap_files: ["run_1/forces.csv", "run_2/forces.csv", "run_3/forces.csv"],
    };
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [{ ...VERSION, questions: [shared] }],
    };
    renderQuestions(document, vi.fn());
    expect(screen.getByRole("textbox", { name: "What unit is field_1 in?" })).toHaveAccessibleDescription(
      /3 files, such as run_1\/forces\.csv › field_1 › unit/,
    );
  });

  it("names the metadata record value a question fills, with its suggestion", () => {
    const title: DocumentQuestion = {
      question_id: `q-${(200).toString(16).padStart(16, "0")}`,
      question_prompt: "What is the dataset's title?",
      gap_property: "titles[0].title",
      suggested_answer: "Soil pH and nitrate readings",
      suggestion_derivation: "model",
    };
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [{ ...VERSION, questions: [title] }],
    };
    renderQuestions(document, vi.fn());
    expect(screen.getByRole("textbox", { name: "What is the dataset's title?" })).toHaveAccessibleDescription(
      /titles\[0\]\.title/,
    );
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

  it("puts a model's suggestions in their boxes, marked, and records them only when accepted", async () => {
    const suggested = (n: number, unit: string): DocumentQuestion => ({
      ...cell(n),
      suggested_answer: unit,
      suggestion_derivation: "model",
    });
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [
        {
          ...VERSION,
          questions: [suggested(1, "mg/kg"), suggested(2, "cm"), suggested(3, "degC"), cell(4)],
        },
      ],
    };
    const answer = vi.fn<ProjectApi["answer"]>().mockResolvedValue(ANSWERED);
    const { container } = renderQuestions(document, answer);
    const check = screen.getByRole("group", { name: "Suggested answers to check (3)" });
    expect(screen.getByRole("group", { name: "Only you can answer these (1)" })).toBeVisible();
    const box = (n: number) => screen.getByRole("textbox", { name: `What unit is field_${n} in?` });
    expect(box(1)).toHaveValue("mg/kg");
    expect(box(1)).toHaveAccessibleDescription(/Suggested by a model/);
    expect(box(4)).toHaveValue("");
    expect(await axe(container)).toHaveNoViolations();

    // Saving the researcher's own answers never sends a suggestion.
    expect(screen.getByRole("button", { name: "Save answers" })).toBeDisabled();

    await userEvent.type(box(1), " dry weight");
    expect(box(1)).toHaveAccessibleDescription(/You changed the suggestion by a model/);
    await userEvent.clear(box(3));
    await userEvent.click(within(check).getByRole("button", { name: "Accept 2 suggested answers" }));
    expect(answer).toHaveBeenCalledWith(ANSWERED.project_id, README.document_id, VERSION.version, [
      { answered_question: cell(1).question_id, answer_text: "mg/kg dry weight" },
      { answered_question: cell(2).question_id, answer_text: "cm" },
    ]);
  });

  it("says when a suggestion is the researcher's own answer for another document, and records it only when accepted", async () => {
    const title: DocumentQuestion = {
      question_id: "q-" + "1".repeat(16),
      question_prompt: "Title: the dataset's title.",
      gap_section: "General information",
      gap_part: "Title",
      shared_field: "title",
      suggested_answer: "Soil cores from Hallam Moor",
      suggestion_derivation: "answer",
      suggested_from: "metadata_record",
    };
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [{ ...VERSION, questions: [title] }],
    };
    const answer = vi.fn<ProjectApi["answer"]>().mockResolvedValue(ANSWERED);
    renderQuestions(document, answer);
    const box = screen.getByRole("textbox", { name: title.question_prompt });
    expect(box).toHaveValue("Soil cores from Hallam Moor");
    expect(box).toHaveAccessibleDescription(/your answer for the metadata record/);
    expect(box).not.toHaveAccessibleDescription(/by a model/);
    expect(answer).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Accept 1 suggested answer" }));
    expect(answer).toHaveBeenCalledWith(ANSWERED.project_id, README.document_id, VERSION.version, [
      { answered_question: title.question_id, answer_text: "Soil cores from Hallam Moor" },
    ]);
  });

  it("puts a changed suggestion back when asked", async () => {
    const document: ProjectDocument = {
      ...UNANSWERED,
      versions: [
        { ...VERSION, questions: [{ ...cell(1), suggested_answer: "mg/kg", suggestion_derivation: "model" }] },
      ],
    };
    renderQuestions(document, vi.fn());
    const box = screen.getByRole("textbox", { name: "What unit is field_1 in?" });
    await userEvent.clear(box);
    expect(screen.getByRole("button", { name: "Accept 0 suggested answers" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Put the suggestion back/ }));
    expect(box).toHaveValue("mg/kg");
  });

  it("links each question to a new conversation about it", () => {
    renderQuestions(UNANSWERED, vi.fn());
    const link = screen.getByRole("link", {
      name: "Talk this through in a new conversation: What unit is field_1 in?",
    });
    expect(link).toHaveAttribute(
      "href",
      `/?question=${encodeURIComponent(`${README.document_id}/${cell(1).question_id}`)}`,
    );
  });

  it("on a version that asks first, saves the answers typed and then asks for the README", async () => {
    const answer = vi.fn().mockResolvedValue(ANSWERED);
    const onWrite = vi.fn();
    renderQuestions(UNANSWERED, answer, onWrite);
    expect(screen.getByRole("button", { name: "Write the README" })).toBeEnabled();
    await userEvent.type(screen.getByRole("textbox", { name: "What unit is field_1 in?" }), "kg");
    await userEvent.click(screen.getByRole("button", { name: "Save and write the README" }));
    expect(answer).toHaveBeenCalledTimes(1);
    expect(onWrite).toHaveBeenCalledWith("Write the README from my answers.");
  });

  it("does not ask for the README when the answers were not recorded", async () => {
    const answer = vi.fn().mockRejectedValue(new Error("offline"));
    const onWrite = vi.fn();
    renderQuestions(UNANSWERED, answer, onWrite);
    await userEvent.type(screen.getByRole("textbox", { name: "What unit is field_1 in?" }), "kg");
    await userEvent.click(screen.getByRole("button", { name: "Save and write the README" }));
    expect(onWrite).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/not recorded/);
  });

  it("offers to write the README once every question is answered", async () => {
    const onWrite = vi.fn();
    renderQuestions(README, vi.fn(), onWrite);
    await userEvent.click(screen.getByRole("button", { name: "Write the README" }));
    expect(onWrite).toHaveBeenCalledWith("Write the README from my answers.");
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
