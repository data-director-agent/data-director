import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { Question } from "../../conversation/question";
import { QuestionSeries } from "./QuestionSeries";

const DISCIPLINE: Question = {
  question_key: "discipline",
  question_kind: "short_text",
  question_prompt: "What is the discipline or field of study of your research?",
  question_suggestions: ["Natural sciences", "Earth and related environmental sciences", "Biological sciences"],
};
const ASKED_BY = "0190a000-0000-7000-8000-000000000001";

function renderDiscipline() {
  const onAnswer = vi.fn();
  const view = render(
    <QuestionSeries questions={[DISCIPLINE]} askedBy={ASKED_BY} askedByName="orchestrator.model" onAnswer={onAnswer} />,
  );
  return { onAnswer, ...view };
}

function sentWords(onAnswer: ReturnType<typeof vi.fn>): string | undefined {
  const [answers] = onAnswer.mock.calls[0] as [{ given_answers: { answer_words?: string }[] }];
  return answers.given_answers[0]?.answer_words;
}

describe("A short text question with suggested answers", () => {
  it("narrows the suggestions to what is typed and sends the one chosen", async () => {
    const { onAnswer, container } = renderDiscipline();
    const box = screen.getByRole("combobox", { name: "Your answer" });
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.type(box, "environ");
    const [option, ...others] = screen.getAllByRole("option");
    expect(others).toEqual([]);
    expect(option).toHaveTextContent(DISCIPLINE.question_suggestions?.[1] ?? "");
    if (option) await userEvent.click(option);
    expect(box).toHaveValue(DISCIPLINE.question_suggestions?.[1]);
    expect(screen.queryByRole("listbox")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(sentWords(onAnswer)).toBe(DISCIPLINE.question_suggestions?.[1]);
  });

  it("sends the researcher's own words when they match no suggestion", async () => {
    const { onAnswer } = renderDiscipline();
    await userEvent.type(screen.getByRole("combobox", { name: "Your answer" }), "Moorland ecology");
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(sentWords(onAnswer)).toBe("Moorland ecology");
  });
});
