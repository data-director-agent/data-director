import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { Question, ReplyAnswers } from "../../conversation/question";
import { AskedQuestions, QuestionSeries } from "./QuestionSeries";

const CHOICE: Question = {
  question_key: "repository",
  question_kind: "choice",
  question_prompt: "Which repository will you deposit in?",
  question_options: [
    { option_value: "zenodo", option_label: "Zenodo" },
    { option_value: "figshare", option_label: "Figshare", option_help: "A hosted repository." },
  ],
};
const TITLE: Question = {
  question_key: "title",
  question_kind: "short_text",
  question_prompt: "What is the dataset called?",
};
const METHOD: Question = {
  question_key: "method",
  question_kind: "long_text",
  question_prompt: "How were the data collected?",
  question_help: "A few sentences are enough.",
};
const ASKED_BY = "0190a000-0000-7000-8000-000000000001";

function renderSeries(questions: Question[]) {
  const onAnswer = vi.fn();
  const view = render(
    <QuestionSeries questions={questions} askedBy={ASKED_BY} askedByName="orchestrator.model" onAnswer={onAnswer} />,
  );
  return { onAnswer, ...view };
}

describe("QuestionSeries, one question", () => {
  it("offers one choice as radio buttons in a group named by the question", async () => {
    const { onAnswer, container } = renderSeries([CHOICE]);
    const group = screen.getByRole("group", { name: CHOICE.question_prompt });
    expect(group.tagName).toBe("FIELDSET");
    expect(screen.getByRole("radio", { name: /Figshare/ })).toHaveAccessibleDescription("A hosted repository.");
    expect(screen.queryByText(/Question 1 of/)).toBeNull();
    expect(await axe(container)).toHaveNoViolations();

    // By keyboard: Tab to the group, arrow to the second option, Tab to the button and send.
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: "Zenodo" })).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /Figshare/ })).toBeChecked();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    expect(onAnswer).toHaveBeenCalledWith(
      { answer_to: ASKED_BY, given_answers: [{ answered_key: "repository", answer_values: ["figshare"] }] },
      "Figshare",
    );
  });

  it("chooses an option when its label text is clicked, not only the control", async () => {
    renderSeries([CHOICE]);
    expect(screen.getByRole("button", { name: "Send answer" })).toBeDisabled();
    await userEvent.click(screen.getByText("Zenodo"));
    expect(screen.getByRole("radio", { name: "Zenodo" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Send answer" })).toBeEnabled();
  });

  it("offers several choices as checkboxes", async () => {
    const { onAnswer } = renderSeries([{ ...CHOICE, question_multiple: true }]);
    await userEvent.click(screen.getByRole("checkbox", { name: "Zenodo" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Figshare/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(onAnswer).toHaveBeenCalledWith(
      {
        answer_to: ASKED_BY,
        given_answers: [{ answered_key: "repository", answer_values: ["zenodo", "figshare"] }],
      },
      "Zenodo; Figshare",
    );
  });

  it("takes an answer in the researcher's own words where the question allows it", async () => {
    const { onAnswer } = renderSeries([{ ...CHOICE, question_other: true }]);
    await userEvent.click(screen.getByRole("radio", { name: "Something else" }));
    expect(screen.getByRole("button", { name: "Send answer" })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Your answer" }), "Our own repository");
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(onAnswer).toHaveBeenCalledWith(
      {
        answer_to: ASKED_BY,
        given_answers: [{ answered_key: "repository", answer_values: [], answer_words: "Our own repository" }],
      },
      "Our own repository",
    );
  });

  it("answers a long text question in a text area, counting the characters left", async () => {
    const { onAnswer } = renderSeries([METHOD]);
    const area = screen.getByRole("textbox", { name: "Your answer" });
    expect(area.tagName).toBe("TEXTAREA");
    expect(screen.getByRole("group", { name: METHOD.question_prompt })).toHaveAccessibleDescription(
      /A few sentences are enough/,
    );
    await userEvent.type(area, "By survey.");
    expect(screen.getByText("3990 characters left.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(onAnswer).toHaveBeenCalledWith(
      { answer_to: ASKED_BY, given_answers: [{ answered_key: "method", answer_values: [], answer_words: "By survey." }] },
      "By survey.",
    );
  });

  it("can be disabled while a message is sent", () => {
    render(<QuestionSeries questions={[CHOICE]} askedBy={ASKED_BY} onAnswer={vi.fn()} disabled />);
    expect(screen.getByRole("radio", { name: "Zenodo" })).toBeDisabled();
  });
});

describe("QuestionSeries, several questions", () => {
  it("puts them one at a time, then shows the answers to check before sending them together", async () => {
    const { onAnswer, container } = renderSeries([CHOICE, TITLE, METHOD]);
    expect(screen.getByText(/orchestrator.model asks 3 questions for you/)).toBeVisible();
    expect(screen.getByText("Question 1 of 3")).toBeVisible();
    expect(screen.getByRole("group", { name: CHOICE.question_prompt })).toBeVisible();
    expect(screen.queryByRole("group", { name: TITLE.question_prompt })).toBeNull();
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
    expect(await axe(container)).toHaveNoViolations();

    // Next with nothing chosen says what to do instead of moving on.
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/Answer the question, or skip it/)).toBeVisible();
    expect(screen.getByText("Question 1 of 3")).toBeVisible();

    await userEvent.click(screen.getByRole("radio", { name: "Zenodo" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Question 2 of 3")).toBeVisible();
    // The focus moves to the new question, so a screen reader reads it next.
    expect(screen.getByText(TITLE.question_prompt)).toHaveFocus();
    await userEvent.type(screen.getByRole("textbox", { name: "Your answer" }), "Bird counts{Enter}");

    // The last question is skipped; the answers are shown to check.
    expect(screen.getByText("Question 3 of 3")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByRole("heading", { name: "Check your answers" })).toHaveFocus();
    expect(screen.getByText("Skipped")).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();

    // Changing an answer goes back to its question, keeping what was entered.
    await userEvent.click(screen.getByRole("button", { name: `Change your answer to: ${TITLE.question_prompt}` }));
    const title = screen.getByRole("textbox", { name: "Your answer" });
    expect(title).toHaveValue("Bird counts");
    await userEvent.type(title, " 2026");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText("Question 2 of 3")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));

    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));
    const sent: ReplyAnswers = {
      answer_to: ASKED_BY,
      given_answers: [
        { answered_key: "repository", answer_values: ["zenodo"] },
        { answered_key: "title", answer_values: [], answer_words: "Bird counts 2026" },
      ],
    };
    expect(onAnswer).toHaveBeenCalledWith(
      sent,
      `${CHOICE.question_prompt} Zenodo\n${TITLE.question_prompt} Bird counts 2026`,
    );
  });

  it("sends nothing when every question is skipped", async () => {
    const { onAnswer } = renderSeries([CHOICE, TITLE]);
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByRole("button", { name: "Send answers" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/Answer at least one question/);
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("asks for the words when Something else is chosen and left empty", async () => {
    renderSeries([{ ...CHOICE, question_other: true }, TITLE]);
    await userEvent.click(screen.getByRole("radio", { name: "Something else" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/Say what your answer is/)).toBeVisible();
    expect(screen.getByText("Question 1 of 2")).toBeVisible();
  });
});

describe("AskedQuestions", () => {
  it("marks the answers given with an icon and words, and the questions skipped", () => {
    const { container } = render(
      <AskedQuestions
        questions={[CHOICE, TITLE, METHOD]}
        answers={{
          answer_to: ASKED_BY,
          given_answers: [
            { answered_key: "repository", answer_values: ["figshare"] },
            { answered_key: "title", answer_values: [], answer_words: "Bird counts" },
          ],
        }}
      />,
    );
    expect(screen.getByText("Figshare").closest("li")).toHaveTextContent("Figshare (your choice)");
    expect(screen.getByText("Zenodo").closest("li")).not.toHaveTextContent("(your choice)");
    expect(screen.getByText(/Your answer: Bird counts/)).toBeVisible();
    expect(screen.getByText("Skipped")).toBeVisible();
    expect(container.querySelectorAll("svg")).toHaveLength(2);
  });

  it("marks nothing when the researcher typed a reply instead", () => {
    render(<AskedQuestions questions={[CHOICE]} answers={null} />);
    expect(screen.queryByText(/your choice/)).toBeNull();
    expect(screen.queryByText("Skipped")).toBeNull();
  });
});
