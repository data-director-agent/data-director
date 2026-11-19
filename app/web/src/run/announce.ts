/**
 * What a run's state says aloud (#69, #948): the announcer's messages, drawn from the reducer's
 * state and nothing else.
 *
 * Each announcement has a key, and a key is said once: a step is announced when it starts, a
 * failed check when its report arrives, each delegated child and tool call when it starts, and the
 * run's end when it ends. An event that repeats
 * (a second `STEP_STARTED` for the same step) or a state drawn again says nothing new. Errors
 * (`RUN_ERROR`, a malformed event, a stream that closed before the run ended) are assertive;
 * the rest is polite.
 */

import { OUTCOME } from "../manifest/wording";
import type { RunState } from "./reduce";

export interface Announcement {
  /** Says what this announces; an announcement whose key has been said is not said again. */
  key: string;
  message: string;
  assertive: boolean;
}

const CHECK_NAME = { grounding: "The grounding check", sources: "The source check" } as const;

function stepLabel(state: RunState, id: string): string {
  return state.steps.find((step) => step.id === id)?.label ?? id;
}

/** The run's end, if it has ended. */
function ending(state: RunState): Announcement | null {
  switch (state.phase) {
    case "finished": {
      const status = state.envelope?.outcome.status;
      const label = status ? OUTCOME[status].label : "Finished";
      return { key: "end", message: `Run finished: ${label}.`, assertive: false };
    }
    case "cancelled":
      return { key: "end", message: "Run cancelled.", assertive: false };
    case "error":
      return {
        key: "end",
        message: `The run failed: ${state.error ?? "no reason was given"}.`,
        assertive: true,
      };
    case "interrupted":
      return {
        key: "end",
        message: "The connection closed before the run ended.",
        assertive: true,
      };
    default:
      return null;
  }
}

/** Everything the state warrants saying, in the order it happened. */
export function runAnnouncements(state: RunState): Announcement[] {
  const said: Announcement[] = [];
  let malformed = 0;
  for (const entry of state.log) {
    if (entry.kind === "step-started") {
      said.push({
        key: `step:${entry.step}`,
        message: `${stepLabel(state, entry.step)} started.`,
        assertive: false,
      });
    } else if (entry.kind === "report" && !entry.passed) {
      said.push({
        key: `report:${entry.check}`,
        message: `${CHECK_NAME[entry.check]} did not pass.`,
        assertive: false,
      });
    } else if (entry.kind === "subagent" && entry.event === "SUBAGENT_STARTED" && entry.runId) {
      said.push({
        key: `subagent:${entry.runId}`,
        message: `Asking ${entry.name ?? "another agent"}.`,
        assertive: false,
      });
    } else if (entry.kind === "tool-call") {
      said.push({ key: `tool:${entry.id}`, message: `Using ${entry.name}.`, assertive: false });
    } else if (entry.kind === "malformed") {
      malformed += 1;
      said.push({
        key: `malformed:${malformed}`,
        message: "An update from the run could not be read; the run carries on.",
        assertive: true,
      });
    }
  }
  const end = ending(state);
  if (end) said.push(end);
  return said;
}

/** What the state warrants that has not been said, each key once. */
export function unsaid(state: RunState, said: ReadonlySet<string>): Announcement[] {
  const seen = new Set(said);
  return runAnnouncements(state).filter(({ key }) => {
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
