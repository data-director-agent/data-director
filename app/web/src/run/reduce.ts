/**
 * One run's state, made from its AG-UI events and nothing else (#69, #947).
 *
 * `reduce` is pure: it takes the state and one event as it arrived (unparsed) and gives the next
 * state, never throwing. The run view, its live-region announcements and the activity log are all
 * drawn from what it gives.
 *
 * - The steps are the plan's (`CUSTOM dd.plan`), named by the harness, so the shell names no stage
 *   of its own. A step that starts while an earlier one is still waiting means the earlier one was
 *   not reached: a run referred at the policy gate goes straight to the checks.
 * - A reply's text is shown whole: `TEXT_MESSAGE_*` content is kept until the message ends. Until
 *   #159 settles streamed replies, the text comes with the envelope instead.
 * - Tool calls and subagent events are entries in the log, from which the run view draws what the
 *   agent is doing (`agentActivity`); reasoning is counted, not shown.
 * - A type or `CUSTOM` name the shell does not know is counted, as is an event that arrives after
 *   the run has ended. A malformed event is counted and logged, and the run carries on.
 * - The end of the stream is not an event: `streamEnded` says a run that had not finished was
 *   interrupted, rather than inventing a finish.
 */

import { parseEvent, type PlanStep, type Subagent } from "./events";
import type { Envelope, GroundingReport, SourceReport } from "./types";

export type StepState = "waiting" | "running" | "finished" | "stopped" | "not-reached";

export type RunPhase = "idle" | "running" | "finished" | "cancelled" | "error" | "interrupted";

export interface RunStep extends PlanStep {
  state: StepState;
}

export type LogEntry =
  | { kind: "step-started" | "step-finished"; step: string }
  | { kind: "report"; check: "grounding" | "sources"; passed: boolean }
  | { kind: "tool-call"; id: string; name: string; done: boolean }
  | ({ kind: "subagent"; event: string } & Subagent)
  | { kind: "malformed"; reason: string };

export interface RunState {
  phase: RunPhase;
  threadId: string | null;
  runId: string | null;
  steps: RunStep[];
  grounding: GroundingReport | null;
  sources: SourceReport | null;
  envelope: Envelope | null;
  /** `RUN_ERROR`'s message. */
  error: string | null;
  /** Replies whose messages have ended, in the order they ended. */
  messages: { id: string; text: string }[];
  /** Text of messages that have started and not yet ended. */
  pending: Readonly<Record<string, string>>;
  log: LogEntry[];
  reasoning: number;
  unrecognised: { count: number; types: string[] };
  malformed: number;
}

export const initialRunState: RunState = {
  phase: "idle",
  threadId: null,
  runId: null,
  steps: [],
  grounding: null,
  sources: null,
  envelope: null,
  error: null,
  messages: [],
  pending: {},
  log: [],
  reasoning: 0,
  unrecognised: { count: 0, types: [] },
  malformed: 0,
};

const ENDED: readonly RunPhase[] = ["finished", "cancelled", "error", "interrupted"];

export function hasEnded(state: RunState): boolean {
  return ENDED.includes(state.phase);
}

function unrecognised(state: RunState, type: string): RunState {
  const { count, types } = state.unrecognised;
  return {
    ...state,
    unrecognised: { count: count + 1, types: types.includes(type) ? types : [...types, type] },
  };
}

function setStep(steps: RunStep[], id: string, state: StepState): RunStep[] {
  if (!steps.some((step) => step.id === id)) return [...steps, { id, label: id, state }];
  return steps.map((step) => (step.id === id ? { ...step, state } : step));
}

function startStep(steps: RunStep[], id: string): RunStep[] {
  const at = steps.findIndex((step) => step.id === id);
  const skipped =
    at < 0
      ? steps
      : steps.map((step, i) =>
          i < at && step.state === "waiting" ? { ...step, state: "not-reached" as const } : step,
        );
  return setStep(skipped, id, "running");
}

/** The steps once the run has ended: none still waiting, none still running. */
function settle(steps: RunStep[], running: StepState): RunStep[] {
  return steps.map((step) => {
    if (step.state === "waiting") return { ...step, state: "not-reached" };
    if (step.state === "running") return { ...step, state: running };
    return step;
  });
}

/** The state after one event, as it arrived from the stream. */
// eslint-disable-next-line complexity -- recorded debt: split it, do not add to it (docs/architecture-review.md)
export function reduce(state: RunState, raw: unknown): RunState {
  const event = parseEvent(raw);

  if (event.type === "MALFORMED") {
    return {
      ...state,
      malformed: state.malformed + 1,
      log: [...state.log, { kind: "malformed", reason: event.reason }],
    };
  }
  if (hasEnded(state)) {
    const type = isTyped(raw) ? raw.type : event.type;
    return unrecognised(state, `${type} after the run ended`);
  }
  // Any event but an error means the run is under way, even if RUN_STARTED was missed.
  const running: RunState =
    state.phase === "idle" && event.type !== "RUN_ERROR" ? { ...state, phase: "running" } : state;

  switch (event.type) {
    case "RUN_STARTED":
      return { ...running, threadId: event.threadId, runId: event.runId };
    case "PLAN":
      return { ...running, steps: event.steps.map((step) => ({ ...step, state: "waiting" })) };
    case "STEP_STARTED":
      return {
        ...running,
        steps: startStep(running.steps, event.stepName),
        log: [...running.log, { kind: "step-started", step: event.stepName }],
      };
    case "STEP_FINISHED":
      return {
        ...running,
        steps: setStep(running.steps, event.stepName, "finished"),
        log: [...running.log, { kind: "step-finished", step: event.stepName }],
      };
    case "GROUNDING":
    case "SOURCES": {
      const check = event.type === "GROUNDING" ? "grounding" : "sources";
      return {
        ...running,
        [check]: event.report,
        log: [...running.log, { kind: "report", check, passed: event.report.passed }],
      };
    }
    case "RUN_FINISHED":
      return {
        ...running,
        phase: "finished",
        envelope: event.result,
        steps: settle(running.steps, "finished"),
      };
    case "RUN_CANCELLED":
      return { ...running, phase: "cancelled", steps: settle(running.steps, "stopped") };
    case "RUN_ERROR":
      return {
        ...running,
        phase: "error",
        error: event.message,
        steps: settle(running.steps, "stopped"),
      };
    case "TEXT_MESSAGE_START":
      return { ...running, pending: { ...running.pending, [event.messageId]: "" } };
    case "TEXT_MESSAGE_CONTENT":
      return {
        ...running,
        pending: {
          ...running.pending,
          [event.messageId]: (running.pending[event.messageId] ?? "") + event.delta,
        },
      };
    case "TEXT_MESSAGE_END": {
      const { [event.messageId]: text = "", ...pending } = running.pending;
      return {
        ...running,
        pending,
        messages: [...running.messages, { id: event.messageId, text }],
      };
    }
    case "TOOL_CALL_START":
      return {
        ...running,
        log: [
          ...running.log,
          { kind: "tool-call", id: event.toolCallId, name: event.toolCallName, done: false },
        ],
      };
    case "TOOL_CALL_END":
      return {
        ...running,
        log: running.log.map((entry) =>
          entry.kind === "tool-call" && entry.id === event.toolCallId
            ? { ...entry, done: true }
            : entry,
        ),
      };
    case "TOOL_CALL_OTHER":
      return running;
    case "SUBAGENT":
      return {
        ...running,
        log: [...running.log, { kind: "subagent", event: event.original, ...event.subagent }],
      };
    case "REASONING":
      return { ...running, reasoning: running.reasoning + 1 };
    case "UNRECOGNISED":
      return unrecognised(running, event.original);
  }
}

function isTyped(raw: unknown): raw is { type: string } {
  return (
    typeof raw === "object" && raw !== null && typeof (raw as { type?: unknown }).type === "string"
  );
}

/**
 * The state once the stream has closed. A run that had not finished, been cancelled or failed
 * was interrupted: the step that was running is stopped, and no finish is invented.
 */
export function streamEnded(state: RunState): RunState {
  if (hasEnded(state)) return state;
  return { ...state, phase: "interrupted", steps: settle(state.steps, "stopped") };
}

/** The state after every event of a stream that has closed, such as a cassette. */
export function reduceAll(events: Iterable<unknown>): RunState {
  let state = initialRunState;
  for (const event of events) state = reduce(state, event);
  return streamEnded(state);
}
