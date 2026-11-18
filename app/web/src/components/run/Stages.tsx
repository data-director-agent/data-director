/**
 * A run's stages as its stream reports them (checklist item 1): the plan's steps, each with a word
 * for its state, drawn from the run reducer's state (#949). A check that finished is told as
 * passed or failed by its report. The stages are the harness's (`dd.plan`); the shell names none of
 * its own.
 */

import "./Stages.css";

import { STAGE_STATE, type StageState } from "../../manifest/wording";
import type { RunState, RunStep } from "../../run/reduce";

const MARK: Record<StageState, string> = {
  waiting: "○",
  running: "●",
  passed: "✓",
  failed: "✗",
  stopped: "!",
  finished: "✓",
  "not-reached": "–",
};

/** The step's state, with a finished check's told by its report. */
function stageState(step: RunStep, run: RunState): StageState {
  if (step.state !== "finished") return step.state;
  const report = step.id === "grounding" ? run.grounding : step.id === "sources" ? run.sources : null;
  if (report === null) return "finished";
  return report.passed ? "passed" : "failed";
}

export function Stages({ run }: { run: RunState }) {
  return (
    <section className="stages-section" aria-label="Progress">
      <h4>Progress</h4>
      {run.steps.length === 0 ? (
        <p className="muted">Starting the run…</p>
      ) : (
        <ol className="stages">
          {run.steps.map((step) => {
            const state = stageState(step, run);
            const { label, tone } = STAGE_STATE[state];
            return (
              <li key={step.id} className={`stage stage-${state}`}>
                <span className="stage-mark" aria-hidden="true">
                  {MARK[state]}
                </span>
                <span className="stage-name">{step.label}</span>
                <span className={tone === "plain" ? "stage-state" : `status status-${tone}`}>
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
