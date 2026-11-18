/**
 * The activity log, a page of its own in the main navigation (#69, #949): each step of each run
 * this tab has streamed, as it happens, newest run first. It is drawn from the same reducer state
 * as the run view (`run/activity.tsx`). The server keeps each run's record but not its steps, so
 * the log holds only what this tab has seen since it was opened, and says so.
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

const CHECK = { grounding: "The grounding check", sources: "The source check" } as const;

function stepLabel(run: RunState, id: string): string {
  return run.steps.find((step) => step.id === id)?.label ?? id;
}

/** Where the run stands, in a word or two. */
function phaseLabel(run: RunState): string {
  switch (run.phase) {
    case "idle":
      return "Starting";
    case "running":
      return "Running";
    case "finished": {
      const status = run.envelope?.outcome.status;
      return status ? `Finished: ${OUTCOME[status].label}` : "Finished";
    }
    case "cancelled":
      return "Cancelled";
    case "error":
      return "Failed";
    case "interrupted":
      return "Interrupted: the connection closed before the run ended";
  }
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
}: {
  run: ActivityRun;
  /** The run's place in the order the tab sent them, from 1. */
  number: number;
}) {
  const headingId = `activity-${key}`;
  return (
    <li>
      <article className="activity-run" aria-labelledby={headingId}>
        <h2 id={headingId}>
          Run {number}, sent at {formatTime(startedAt, { timeStyle: "medium" })}
        </h2>
        <p>
          {phaseLabel(state)}.{" "}
          <Link to={homePath({ conversation: conversationId })}>Open its conversation</Link>
        </p>
        {state.log.length > 0 && (
          <ol className="activity-entries">
            {state.log.map((entry, i) => (
              <li key={i}>
                <Entry entry={entry} run={state} />
              </li>
            ))}
          </ol>
        )}
        {state.phase === "error" && state.error && <p>The run failed: {state.error}</p>}
        <UnrecognisedEvents run={state} />
      </article>
    </li>
  );
}

export function ActivityLog() {
  const { runs } = useRunActivity();
  return (
    <>
      <PageHeader title="Activity log" />
      <p className="hint">
        Each step of each run this tab has sent, as it happens. Data Director keeps each run's
        record but not its steps, so only the runs sent from this tab since it was opened are
        listed.
      </p>
      {runs.length === 0 ? (
        <p>No runs in this tab yet. Send a message in a conversation to start one.</p>
      ) : (
        <ol className="activity-runs">
          {runs.map((run, i) => (
            <Run key={run.key} run={run} number={runs.length - i} />
          ))}
        </ol>
      )}
    </>
  );
}
