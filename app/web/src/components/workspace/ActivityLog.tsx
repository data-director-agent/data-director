/**
 * The activity log, a page of its own in the main navigation (#69, #949, #1330): each step of each
 * run this tab has streamed, as it happens, newest run first, and below them every run Data
 * Director has recorded for the person (`RecordedRuns`). The steps are drawn from the same reducer
 * state as the run view (`run/activity.tsx`); the server keeps each run's record but not its steps,
 * so only the runs sent from this tab since it was opened are shown step by step, and the page says
 * so. The recorded runs outlast a reload, so the log is never blank once a run has been recorded.
 *
 * A delegated child is an entry of its parent's run, linked to its record in the run store. The
 * log is not a live region: the run's progress is said once, by the run view, through the
 * announcer.
 */

import "./ActivityLog.css";

import { formatTime } from "../../format";
import { OUTCOME } from "../../manifest/wording";
import { type ActivityRun, useRunActivity } from "../../run/activity";
import type { LogEntry, RunState } from "../../run/reduce";
import { homePath, Link } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { UnrecognisedEvents } from "../run/UnrecognisedEvents";
import { RecordedRuns } from "./RecordedRuns";

const CHECK = { grounding: "The grounding check", sources: "The source check" } as const;

function stepLabel(run: RunState, id: string): string {
  return run.steps.find((step) => step.id === id)?.label ?? id;
}

type Tone = "ok" | "warn" | "danger" | "undeclared";

/** Where the run stands, in a word or two, with the tone of its badge (never colour alone). */
function phaseBadge(run: RunState): { label: string; tone: Tone; note?: string } {
  switch (run.phase) {
    case "idle":
      return { label: "Starting", tone: "undeclared" };
    case "running":
      return { label: "Running", tone: "undeclared" };
    case "finished": {
      const status = run.envelope?.outcome.status;
      return status
        ? { label: `Finished: ${OUTCOME[status].label}`, tone: OUTCOME[status].tone }
        : { label: "Finished", tone: "ok" };
    }
    case "cancelled":
      return { label: "Cancelled", tone: "warn" };
    case "error":
      return { label: "Failed", tone: "danger" };
    case "interrupted":
      return {
        label: "Interrupted",
        tone: "warn",
        note: "The connection closed before the run ended.",
      };
  }
}

/** A run still under way stays open; finished ones fold away so the newest stays in view. */
function isLive(run: RunState): boolean {
  return run.phase === "idle" || run.phase === "running";
}

/** The invocations this tab's runs show step by step: each run's own and its delegated children. */
function heldInvocations(runs: readonly ActivityRun[]): Set<string> {
  const held = new Set<string>();
  for (const { state } of runs) {
    if (state.envelope) held.add(state.envelope.invocation_id);
    for (const entry of state.log) {
      if (entry.kind === "subagent" && entry.runId) held.add(entry.runId);
    }
  }
  return held;
}

function Subagent({ entry }: { entry: Extract<LogEntry, { kind: "subagent" }> }) {
  const what =
    entry.event === "SUBAGENT_STARTED"
      ? `Delegated to ${entry.name ?? "another agent"}`
      : entry.event === "SUBAGENT_FINISHED"
        ? `Delegated run finished${entry.status ? `: ${entry.status}` : ""}`
        : entry.event === "SUBAGENT_ERROR"
          ? "Delegated run failed"
          : `Delegated run: ${entry.event}`;
  return (
    <>
      {what}
      {entry.runId && (
        <>
          {" "}
          (<Link to={homePath({ run: entry.runId })}>open its run</Link>)
        </>
      )}
    </>
  );
}

function Entry({ entry, run }: { entry: LogEntry; run: RunState }) {
  switch (entry.kind) {
    case "step-started":
      return <>{stepLabel(run, entry.step)} started</>;
    case "step-finished":
      return <>{stepLabel(run, entry.step)} done</>;
    case "report":
      return (
        <>
          {CHECK[entry.check]} {entry.passed ? "passed" : "did not pass"}
        </>
      );
    case "tool-call":
      return (
        <>
          Tool call <code>{entry.name}</code> {entry.done ? "done" : "under way"}
        </>
      );
    case "subagent":
      return <Subagent entry={entry} />;
    case "malformed":
      return <span className="status status-danger">Malformed event from server: {entry.reason}</span>;
  }
}

function Run({
  run: { key, conversationId, startedAt, state },
  number,
  newest,
}: {
  run: ActivityRun;
  /** The run's place in the order the tab sent them, from 1. */
  number: number;
  newest: boolean;
}) {
  const headingId = `activity-${key}`;
  const badge = phaseBadge(state);
  const steps = state.log.length;
  return (
    <li>
      <article className="activity-run" aria-labelledby={headingId}>
        <h3 id={headingId}>
          Run {number}, sent at {formatTime(startedAt, { timeStyle: "medium" })}
        </h3>
        <p className="activity-summary">
          <span className={`status status-${badge.tone}`}>{badge.label}</span>
          {badge.note && <span> {badge.note}</span>}{" "}
          <Link to={homePath({ conversation: conversationId })}>Open its conversation</Link>
        </p>
        {state.phase === "error" && state.error && <p>The run failed: {state.error}</p>}
        {steps > 0 && (
          <details open={newest || isLive(state)} className="activity-details">
            <summary>{steps === 1 ? "1 step" : `${steps} steps`}</summary>
            <ol className="activity-entries">
              {state.log.map((entry, i) => (
                <li key={i}>
                  <Entry entry={entry} run={state} />
                </li>
              ))}
            </ol>
          </details>
        )}
        <UnrecognisedEvents run={state} />
      </article>
    </li>
  );
}

export function ActivityLog() {
  const { runs } = useRunActivity();
  const ended = runs.filter(({ state }) => !isLive(state)).length;
  return (
    <>
      <PageHeader title="Activity log" />
      <p className="hint">
        Every run Data Director has recorded for you, with its outcome. Data Director keeps each
        run's record but not its steps, so the steps are shown only for runs sent from this tab
        since it was opened.
      </p>
      {runs.length > 0 && (
        <section aria-labelledby="this-tab-runs">
          <h2 id="this-tab-runs">Sent from this tab</h2>
          {runs.length > 1 && <p>{runs.length} runs, newest first.</p>}
          <ol className="activity-runs">
            {runs.map((run, i) => (
              <Run key={run.key} run={run} number={runs.length - i} newest={i === 0} />
            ))}
          </ol>
        </section>
      )}
      <RecordedRuns shownAbove={heldInvocations(runs)} refresh={ended} />
    </>
  );
}
