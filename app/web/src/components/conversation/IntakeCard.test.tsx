import { createRef } from "react";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

// Written by the server (app/tests/test_intake_routes.py): a new project's intake, asking the
// entry question, and an intake completed from entry 1.
import completeFixture from "../../../fixtures/intake-complete.json";
import pendingFixture from "../../../fixtures/intake-pending.json";
import flowFixture from "../../../fixtures/process-flow.json";
import type { ProcessFlow } from "../../flow/types";
import { DecisionConflict, type ProjectIntake } from "../../project/api";
import { Button } from "../ui/Button";
import { IntakeCard } from "./IntakeCard";
import type { QuestionFocus } from "./QuestionSeries";

const PENDING = pendingFixture as ProjectIntake;
const COMPLETE = completeFixture as ProjectIntake;
const FLOW = flowFixture as ProcessFlow;

function first<T>(items: T[]): T {
  const item = items[0];
  if (item === undefined) throw new Error("the fixture has no item");
  return item;
}

const ENTRY = first(PENDING.questions);
const ENTRY_OPTION = first(ENTRY.question.question_options ?? []);

function renderCard(props: Partial<Parameters<typeof IntakeCard>[0]> = {}) {
  const handlers = {
    onAnswer: vi.fn<(id: string, values: string[]) => Promise<ProjectIntake>>(() =>
      Promise.resolve(COMPLETE),
    ),
    onDismiss: vi.fn(),
    onClose: vi.fn(),
    onAnnounce: vi.fn<(text: string) => void>(),
  };
  const view = render(<IntakeCard intake={PENDING} flow={FLOW} {...handlers} {...props} />);
  return { ...view, ...handlers };
}

describe("IntakeCard", () => {
  it("asks the next question as a choice and announces it, without taking the focus", async () => {
    const { container, onAnnounce } = renderCard();
    const group = screen.getByRole("group", { name: ENTRY.question.question_prompt });
    expect(within(group).getAllByRole("radio")).toHaveLength(
      ENTRY.question.question_options?.length ?? 0,
    );
    expect(onAnnounce).toHaveBeenCalledWith(expect.stringContaining(ENTRY.question.question_prompt));
    expect(document.activeElement).toBe(document.body);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("records the chosen option for the question's id", async () => {
    const { onAnswer } = renderCard();
    await userEvent.click(screen.getByRole("radio", { name: ENTRY_OPTION.option_label }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onAnswer).toHaveBeenCalledWith(ENTRY.question_id, [ENTRY_OPTION.option_value]);
  });

  it("asks for an answer or a skip when Next is pressed with nothing chosen", async () => {
    const { onAnswer } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: ENTRY.question.question_prompt })).toHaveClass(
      "field-invalid",
    );
  });

  it("says why an answer was refused and keeps what was chosen", async () => {
    const refused = new DecisionConflict({
      type: "about:blank",
      title: "Data Director could not record this answer",
      detail: "not an option of the question",
    });
    renderCard({ onAnswer: vi.fn(() => Promise.reject(refused)) });
    await userEvent.click(screen.getByRole("radio", { name: ENTRY_OPTION.option_label }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText(/not an option of the question/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: ENTRY_OPTION.option_label })).toBeChecked();
  });

  it("dismisses the intake from Skip these questions", async () => {
    const { onDismiss, onClose } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Skip these questions" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("passes one question by with Skip, recording nothing", async () => {
    const { onAnswer } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.queryByRole("group", { name: ENTRY.question.question_prompt })).toBeNull();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("names the phase the project starts at and the suggested step once complete", async () => {
    const { onAnnounce, container } = renderCard({ intake: COMPLETE });
    const entry = FLOW.entries.find((e) => e.number === COMPLETE.progress.entry);
    const phase = FLOW.phases.find((p) => p.number === entry?.starts_at);
    const step = FLOW.phases.flatMap((p) => p.steps).find((s) => s.id === COMPLETE.progress.suggested);
    if (!phase || !step) throw new Error("the fixtures do not agree");
    expect(screen.getByText(new RegExp(phase.name))).toBeInTheDocument();
    expect(screen.getByText(step.label)).toBeInTheDocument();
    expect(onAnnounce).toHaveBeenLastCalledWith(expect.stringContaining(step.label));
    expect(await axe(container)).toHaveNoViolations();
  });

  it("asked again, walks every question with its answer chosen, recording only a change", async () => {
    const { onAnswer, onClose, onDismiss } = renderCard({ intake: COMPLETE, again: true });
    for (const asked of COMPLETE.questions) {
      const group = screen.getByRole("group", { name: asked.question.question_prompt });
      const chosen = within(group)
        .getAllByRole("radio")
        .filter((r) => (r as HTMLInputElement).checked)
        .map((r) => (r as HTMLInputElement).value);
      expect(chosen).toEqual(asked.answer_values);
      await userEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(onAnswer).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { level: 4 })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("once complete, offers to start the conversation with the suggested step", async () => {
    const onStart = vi.fn<(message: string) => void>();
    const { container, onClose } = renderCard({ intake: COMPLETE, onStart });
    const step = FLOW.phases.flatMap((p) => p.steps).find((s) => s.id === COMPLETE.progress.suggested);
    if (!step) throw new Error("the fixtures do not agree");
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: `Start with ${step.label}` }));
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onStart).toHaveBeenCalledWith(expect.stringContaining(step.label));
    expect(onClose).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("once complete, offers only Close when the conversation has begun", () => {
    renderCard({ intake: COMPLETE });
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Start with/ })).not.toBeInTheDocument();
  });

  // The intake once Data Director has recorded the entry point from what the researcher said.
  const BY_MODEL: ProjectIntake = {
    ...COMPLETE,
    progress: { ...COMPLETE.progress, entry_source: "model" },
  };
  const MODEL_ENTRY = first(BY_MODEL.questions);

  function chosenIn(prompt: string): string[] {
    return within(screen.getByRole("group", { name: prompt }))
      .getAllByRole("radio")
      .filter((r) => (r as HTMLInputElement).checked)
      .map((r) => (r as HTMLInputElement).value);
  }

  it("offers the entry point Data Director worked out, chosen and marked, to confirm", async () => {
    const { container, onAnswer } = renderCard({ intake: BY_MODEL });
    expect(chosenIn(MODEL_ENTRY.question.question_prompt)).toEqual(MODEL_ENTRY.answer_values);
    expect(screen.getByRole("note")).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onAnswer).toHaveBeenCalledWith(MODEL_ENTRY.question_id, MODEL_ENTRY.answer_values);
  });

  it("asked again, records the entry point Data Director worked out once confirmed", async () => {
    const { onAnswer } = renderCard({ intake: BY_MODEL, again: true });
    expect(chosenIn(MODEL_ENTRY.question.question_prompt)).toEqual(MODEL_ENTRY.answer_values);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onAnswer).toHaveBeenCalledWith(MODEL_ENTRY.question_id, MODEL_ENTRY.answer_values);
  });

  it("records nothing when the entry point Data Director worked out is skipped", async () => {
    const { onAnswer } = renderCard({ intake: BY_MODEL });
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.queryByRole("group", { name: MODEL_ENTRY.question.question_prompt })).toBeNull();
  });

  it("asked again, closes from Skip these questions without dismissing", async () => {
    const { onClose, onDismiss } = renderCard({ intake: COMPLETE, again: true });
    await userEvent.click(screen.getByRole("button", { name: "Skip these questions" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onDismiss).not.toHaveBeenCalled();
  });
  it("shows an answer's notice as soon as it is chosen, and keeps it once recorded", async () => {
    const notice = "Please do not paste the sensitive data itself.";
    const sensitive = {
      question_id: "intake.sensitive",
      question: {
        ...ENTRY.question,
        question_key: "sensitive",
        question_prompt: "Does the data include sensitive information?",
        question_options: [
          { option_value: "yes", option_label: "Yes" },
          { option_value: "no", option_label: "No" },
        ],
      },
      answer_values: null,
      notices: { yes: notice },
    };
    const intake: ProjectIntake = {
      ...PENDING,
      questions: [{ ...ENTRY, answer_values: [ENTRY_OPTION.option_value] }, sensitive],
    };
    const { rerender, ...handlers } = renderCard({ intake });
    expect(screen.queryByRole("note")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "No" }));
    expect(screen.queryByRole("note")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "Yes" }));
    expect(screen.getByRole("note").textContent).toBe(notice);
    // Recorded, the notice stays while the card goes on.
    const recorded: ProjectIntake = {
      ...intake,
      questions: [intake.questions[0] as (typeof intake.questions)[0], { ...sensitive, answer_values: ["yes"] }],
    };
    rerender(<IntakeCard intake={recorded} flow={FLOW} {...handlers} />);
    expect(screen.getByRole("note").textContent).toBe(notice);
  });
  it("leads the question's actions with what the page gives to attach a file", () => {
    renderCard({ attach: <Button>Attach a file</Button> });
    const form = screen.getByRole("group", { name: ENTRY.question.question_prompt }).closest("form");
    if (!form) throw new Error("no form");
    const actions = within(form).getAllByRole("button");
    const attach = within(form).getByRole("button", { name: "Attach a file" });
    const next = within(form).getByRole("button", { name: "Next" });
    expect(actions.indexOf(attach)).toBeLessThan(actions.indexOf(next));
  });

  it("announces nothing while hidden behind another way of replying", () => {
    const { onAnnounce } = renderCard({ hidden: true });
    expect(onAnnounce).not.toHaveBeenCalled();
  });

  it("moves the focus to the question when asked to", () => {
    const focus = createRef<QuestionFocus>();
    renderCard({ ref: focus });
    act(() => focus.current?.focus());
    expect(screen.getByText(ENTRY.question.question_prompt).closest("legend")).toHaveFocus();
  });
});
