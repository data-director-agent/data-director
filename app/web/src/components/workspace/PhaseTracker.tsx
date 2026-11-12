/**
 * The journey from planning a dataset to sharing it, in a researcher's words: six phases, each
 * with the things they will do in it. It names no agent and no Blueprint requirement; which
 * agents help is for the conversation to say. The phases come from the server's process flow, so
 * the shell keeps no copy of it.
 *
 * Drawn as a strip, like a progress bar, opening to show each phase's steps. Where the project
 * is comes from the harness, which derives it from the project log on every read
 * (docs/specs/orchestration.md): the entry point the researcher chose, each step started, done or
 * skipped, and the step to suggest next. Data Director may record the entry point from what the
 * researcher said, which the strip says, until they choose one themselves; with none recorded,
 * nothing is suggested. The shell computes none of it. The suggestion is never
 * a gate: the researcher may mark any step done or skipped, or open it again, for the many steps
 * nothing in the project records, and may do the steps in any order.
 */

import "./PhaseTracker.css";

import type {
  FlowStep,
  ProcessFlow,
  ProjectProgress,
  StepMark,
  StepState,
} from "../../flow/types";
import { ListChecks } from "lucide-react";

import { Button } from "../ui/Button";

export type FlowLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; flow: ProcessFlow };

/** The project's progress and how to change it; absent until the conversation has a project. */
export interface TrackedProgress {
  progress: ProjectProgress;
  chooseEntry(entry: number): void;
  markStep(stepId: string, mark: StepMark): void;
  /** Why the last change was not recorded, if it was not. */
  error?: string | null;
  /** Opens the intake card with the current answers chosen (docs/specs/app.md, rule 25). */
  answerIntakeAgain?: () => void;
}

const STATE_LABEL: Record<StepState, string> = {
  done: "Done",
  started: "Started",
  skipped: "Skipped",
};

export function PhaseTracker({
  load,
  tracked,
}: {
  load: FlowLoad;
  tracked?: TrackedProgress | null;
}) {
  const flow = load.state === "loaded" ? load.flow : null;
  const suggested =
    flow && tracked ? stepById(flow, tracked.progress.suggested) : null;
  return (
    <nav
      aria-labelledby="phases-heading"
      className="workspace-phases phase-strip"
    >
      <div className="phase-strip-head">
        <h2 id="phases-heading">Your data journey</h2>
        {!tracked && (
          <p className="phase-strip-where">
            Where your project is shows here once your conversation has a
            project.
          </p>
        )}
        {tracked && flow && (
          <>
            <label className="phase-strip-entry">
              Where you started{" "}
              <select
                value={tracked.progress.entry ?? ""}
                onChange={(e) => tracked.chooseEntry(Number(e.target.value))}
              >
                {tracked.progress.entry === null && (
                  <option value="">Not said yet</option>
                )}
                {flow.entries.map((entry) => (
                  <option key={entry.number} value={entry.number}>
                    {capitalised(entry.text)}
                  </option>
                ))}
              </select>
            </label>
            {tracked.progress.entry !== null &&
              tracked.progress.entry_source === "model" && (
                <p className="phase-strip-where muted">
                  Set by Data Director from what you said.
                </p>
              )}
            <p className="phase-strip-where" role="status">
              {suggested ? (
                <>
                  Suggested next: <strong>{suggested.label}</strong>
                </>
              ) : tracked.progress.entry === null ? (
                "Choose where you started, or tell Data Director, to get a suggested next step."
              ) : (
                "Every step from where you started is done or skipped."
              )}
            </p>
            {tracked.answerIntakeAgain && (
              <Button size="small" icon={ListChecks} onPress={tracked.answerIntakeAgain}>
                Answer the setup questions again
              </Button>
            )}
          </>
        )}
      </div>
      {tracked?.error && (
        <p role="alert" className="callout status-danger">
          Data Director could not record that: {tracked.error}.
        </p>
      )}
      {load.state === "loading" && <p role="status">Loading the journey…</p>}
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not load the journey: {load.message}.</p>
        </div>
      )}
      {flow && (
        <>
          <ol className="phase-bar" aria-label="The phases in order">
            {flow.phases.map((phase) => {
              const counted = phase.steps.filter((s) => !s.out_of_scope);
              const finished = counted.filter((s) => {
                const state = tracked?.progress.steps[s.id];
                return state === "done" || state === "skipped";
              }).length;
              return (
                <li key={phase.number} className="phase-bar-segment">
                  <span className="phase-bar-number" aria-hidden="true">
                    {phase.number}
                  </span>
                  <span className="phase-bar-title">{phase.name}</span>
                  {tracked && (
                    <span className="phase-bar-count muted">
                      {finished} of {counted.length} done or skipped
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
          <details className="phase-strip-details">
            <summary>Show what happens in each phase</summary>
            <Phases flow={flow} tracked={tracked ?? null} />
          </details>
        </>
      )}
    </nav>
  );
}

function Phases({
  flow,
  tracked,
}: {
  flow: ProcessFlow;
  tracked: TrackedProgress | null;
}) {
  return (
    <ol className="phase-list">
      {flow.phases.map((phase) => (
        <li key={phase.number}>
          <details>
            <summary>
              <span className="phase-number">Phase {phase.number}</span>{" "}
              {phase.name}
            </summary>
            <p className="phase-summary">{phase.summary}</p>
            <ol className="step-list">
              {phase.steps.map((step) => (
                <li key={step.id}>
                  <Step step={step} tracked={tracked} />
                </li>
              ))}
            </ol>
          </details>
        </li>
      ))}
    </ol>
  );
}

function Step({
  step,
  tracked,
}: {
  step: FlowStep;
  tracked: TrackedProgress | null;
}) {
  const state = tracked?.progress.steps[step.id];
  const suggested = tracked?.progress.suggested === step.id;
  return (
    <div className="step">
      <p className="step-text">
        {step.label}
        {step.optional && <span className="muted"> (optional)</span>}
        {step.out_of_scope && (
          <span className="muted"> (out of scope for now)</span>
        )}
        {state && (
          <span className={`step-state step-state-${state}`}>
            {" "}
            {STATE_LABEL[state]}
          </span>
        )}
        {suggested && (
          <span className="step-state step-state-suggested">
            {" "}
            Suggested next
          </span>
        )}
      </p>
      {tracked && !step.out_of_scope && (
        <div className="step-actions">
          {state === "done" || state === "skipped" ? (
            <Button
              size="small"
              variant="quiet"
              aria-label={`Open again: ${step.label}`}
              onPress={() => tracked.markStep(step.id, "open")}
            >
              Open again
            </Button>
          ) : (
            <>
              <Button
                size="small"
                variant="quiet"
                aria-label={`Mark done: ${step.label}`}
                onPress={() => tracked.markStep(step.id, "done")}
              >
                Mark done
              </Button>
              <Button
                size="small"
                variant="quiet"
                aria-label={`Skip: ${step.label}`}
                onPress={() => tracked.markStep(step.id, "skipped")}
              >
                Skip
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function stepById(flow: ProcessFlow, id: string | null): FlowStep | null {
  if (!id) return null;
  for (const phase of flow.phases) {
    const found = phase.steps.find((s) => s.id === id);
    if (found) return found;
  }
  return null;
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
