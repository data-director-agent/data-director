import { render, screen, within } from "@testing-library/react";

import { Markdown } from "../ui/Markdown";
import { type Question, answersText } from "../../conversation/question";

const CHOICE: Question = {
  question_key: "repository",
  question_kind: "choice",
  question_prompt: "Which *repository* will you use?",
  question_multiple: true,
  question_other: true,
  question_options: [
    { option_value: "zenodo", option_label: "Zenodo" },
    { option_value: "figshare", option_label: "Figshare" },
  ],
};
const TITLE: Question = { question_key: "title", question_kind: "short_text", question_prompt: "Its title?" };
const METHOD: Question = { question_key: "method", question_kind: "long_text", question_prompt: "How?" };

function rendered(text: string) {
  return render(<Markdown>{text}</Markdown>).container;
}

describe("answersText", () => {
  it("puts each question in bold, followed by its answer, and says which were skipped", () => {
    const text = answersText([CHOICE, TITLE, METHOD], {
      answer_to: "asked",
      given_answers: [
        { answered_key: "repository", answer_values: ["zenodo", "figshare"], answer_words: "Our own" },
        { answered_key: "method", answer_values: [], answer_words: "1. Counted birds\n# by hand\n\n<b>Then</b> _tallied_" },
      ],
    });
    const page = rendered(text);
    // The questions, as written, each in bold: markup in a prompt is shown, not applied.
    expect([...page.querySelectorAll("strong")].map((s) => s.textContent)).toEqual([
      CHOICE.question_prompt,
      TITLE.question_prompt,
      METHOD.question_prompt,
    ]);
    expect(page.querySelector("em strong, strong em")).toBeNull();
    // Several options chosen are a list, words in place of an option among them.
    const items = within(page.querySelector("ul") as HTMLElement).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    // A skipped question says so.
    expect(page.querySelector("em")).not.toBeNull();
    // The researcher's words are shown as typed, keeping their line breaks and paragraphs.
    expect(page.querySelectorAll("ol, h1, b")).toHaveLength(0);
    expect(screen.getByText(/1\. Counted birds/)).toBeVisible();
    expect(page.querySelectorAll("br")).toHaveLength(1);
    expect(screen.getByText("<b>Then</b> _tallied_")).toBeVisible();
  });

  it("puts a lone answer after its question", () => {
    const text = answersText([TITLE], {
      answer_to: "asked",
      given_answers: [{ answered_key: "title", answer_values: [], answer_words: "Bird counts" }],
    });
    const page = rendered(text);
    expect(page.querySelectorAll("p")).toHaveLength(2);
    expect(page.querySelector("p:last-child")?.textContent).toBe("Bird counts");
  });
});
