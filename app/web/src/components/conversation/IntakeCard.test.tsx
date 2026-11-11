import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

// Written by the server (app/tests/test_intake_routes.py): a new project's intake, asking the
// entry question, and an intake completed from entry 1.
import completeFixture from "../../../fixtures/intake-complete.json";
import pendingFixture from "../../../fixtures/intake-pending.json";
import flowFixture from "../../../fixtures/process-flow.json";
import type { ProcessFlow } from "../../flow/types";
import { DecisionConflict, type ProjectIntake } from "../../project/api";
import { IntakeCard } from "./IntakeCard";

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

  it("asked again, closes from Skip these questions without dismissing", async () => {
    const { onClose, onDismiss } = renderCard({ intake: COMPLETE, again: true });
    await userEvent.click(screen.getByRole("button", { name: "Skip these questions" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
