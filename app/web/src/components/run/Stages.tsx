/**
 * A run's stages as its stream reports them (checklist item 1): the plan's steps, each with a word
 * for its state, drawn from the run reducer's state (#949). A check that finished is told as
 * passed or failed by its report. The stages are the harness's (`dd.plan`); the shell names none of
 * its own.
 *
 * A running stage says how long it has been running, by this page's clock. Under the Agent stage,
 * what the agent has done so far is drawn as it streams (`AgentActivity`).
 */

import "./Stages.css";

import { STAGE_STATE, type StageState } from "../../manifest/wording";
import { hasEnded, type RunState, type RunStep } from "../../run/reduce";
import { AgentActivity } from "./AgentActivity";
import { formatElapsed, useSince } from "./useSince";

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

/** How long the stage has been running; the screen reader hears the state word, not each tick. */
function RunningFor({ id }: { id: string }) {
  const ms = useSince(id, true);
  return <span aria-hidden="true"> · {formatElapsed(ms)}</span>;
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
            const live = state === "running" && !hasEnded(run);
            return (
              <li key={step.id} className={`stage stage-${state}`}>
                <span className="stage-mark" aria-hidden="true">
                  {MARK[state]}
                </span>
                <span className="stage-name">{step.label}</span>
                <span className={tone === "plain" ? "stage-state" : `status status-${tone}`}>
                  {label}
                  {live && <RunningFor id={step.id} />}
                </span>
                {step.id === "agent" && (
                  <AgentActivity run={run} running={live} />
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
