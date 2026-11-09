import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { ChoiceQuestion as Question } from "../../conversation/question";
import { AskedQuestion, ChoiceQuestion } from "./ChoiceQuestion";

const QUESTION: Question = {
  question_prompt: "Which repository will you deposit in?",
  question_options: [
    { option_value: "zenodo", option_label: "Zenodo" },
    { option_value: "figshare", option_label: "Figshare", option_help: "A hosted repository." },
  ],
};
const ASKED_BY = "0190a000-0000-7000-8000-000000000001";

function renderQuestion(question: Question) {
  const onAnswer = vi.fn();
  const view = render(<ChoiceQuestion question={question} askedBy={ASKED_BY} onAnswer={onAnswer} />);
  return { onAnswer, ...view };
}

describe("ChoiceQuestion", () => {
  it("offers one choice as radio buttons in a group named by the question", async () => {
    const { onAnswer, container } = renderQuestion(QUESTION);
    const group = screen.getByRole("group", { name: QUESTION.question_prompt });
    expect(group.tagName).toBe("FIELDSET");
    expect(screen.getByRole("radio", { name: /Figshare/ })).toHaveAccessibleDescription(
      "A hosted repository.",
    );
    expect(await axe(container)).toHaveNoViolations();

    // By keyboard: Tab to the group, arrow to the second option, Tab to the button and send.
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: "Zenodo" })).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /Figshare/ })).toBeChecked();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    expect(onAnswer).toHaveBeenCalledWith(
      { answer_to: ASKED_BY, answer_values: ["figshare"] },
      "Figshare",
    );
  });

  it("chooses an option when its label text is clicked, not only the control", async () => {
    renderQuestion(QUESTION);
    await userEvent.click(screen.getByText("Zenodo"));
    expect(screen.getByRole("radio", { name: "Zenodo" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Send answer" })).toBeEnabled();
  });

  it("offers several choices as checkboxes", async () => {
    const { onAnswer } = renderQuestion({ ...QUESTION, question_multiple: true });
    expect(screen.getByText(/Choose one or more/)).toBeVisible();
    await userEvent.click(screen.getByRole("checkbox", { name: "Zenodo" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Figshare/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(onAnswer).toHaveBeenCalledWith(
      { answer_to: ASKED_BY, answer_values: ["zenodo", "figshare"] },
      "Zenodo; Figshare",
    );
  });

  it("takes an answer in the researcher's own words where the question allows it", async () => {
    const { onAnswer } = renderQuestion({ ...QUESTION, question_other: true });
    await userEvent.click(screen.getByRole("radio", { name: "Something else" }));
    const send = screen.getByRole("button", { name: "Send answer" });
    expect(send).toBeDisabled(); // nothing said yet
    await userEvent.type(screen.getByRole("textbox", { name: "Your answer" }), "Our own repository");
    await userEvent.click(send);
    expect(onAnswer).toHaveBeenCalledWith(
      { answer_to: ASKED_BY, answer_values: [], answer_other: "Our own repository" },
      "Our own repository",
    );
  });

  it("has no 'Something else' where the question takes only its options", () => {
    renderQuestion(QUESTION);
    expect(screen.queryByRole("radio", { name: "Something else" })).toBeNull();
  });
});

describe("AskedQuestion", () => {
  it("marks the option chosen with an icon and words, not colour alone", async () => {
    const { container } = render(
      <AskedQuestion
        question={QUESTION}
        answer={{ answer_to: ASKED_BY, answer_values: ["figshare"] }}
      />,
    );
    const picked = screen.getByText("(your choice)").closest("li");
    expect(picked).toHaveTextContent("Figshare (your choice)");
    expect(screen.getByText("Zenodo").closest("li")).not.toHaveTextContent("your choice");
    expect(screen.queryByRole("radio")).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks nothing when the researcher typed a reply instead", () => {
    render(<AskedQuestion question={QUESTION} answer={null} />);
    expect(screen.queryByText("(your choice)")).toBeNull();
  });
});
