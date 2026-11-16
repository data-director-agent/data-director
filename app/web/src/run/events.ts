/**
 * The AG-UI events of one run, as the shell reads them (docs/specs/transport.md).
 *
 * The harness's binding (`dd_harness.transport.agui`) sends the conductor's plan, its steps, the
 * checks' reports and the outcome. `parseEvent` checks only the fields the reducer reads, so a
 * field it does not know is ignored, not refused. An event with no type, or a known type without
 * the fields it needs, is malformed; a type or `CUSTOM` name the shell does not know is
 * unrecognised. Neither throws.
 *
 * TODO(#946): check `RunEvent` against `@ag-ui/core`'s event types once the transport adds it.
 */

import type { Envelope, GroundingReport, SourceReport } from "./types";

export interface PlanStep {
  id: string;
  label: string;
}

export type RunEvent =
  | { type: "RUN_STARTED"; threadId: string; runId: string }
  | { type: "RUN_FINISHED"; result: Envelope }
  | { type: "RUN_CANCELLED" }
  | { type: "RUN_ERROR"; message: string }
  | { type: "PLAN"; steps: PlanStep[] }
  | { type: "STEP_STARTED"; stepName: string }
  | { type: "STEP_FINISHED"; stepName: string }
  | { type: "GROUNDING"; report: GroundingReport }
  | { type: "SOURCES"; report: SourceReport }
  | { type: "TEXT_MESSAGE_START"; messageId: string }
  | { type: "TEXT_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "TEXT_MESSAGE_END"; messageId: string }
  | { type: "TOOL_CALL_START"; toolCallId: string; toolCallName: string }
  | { type: "TOOL_CALL_END"; toolCallId: string }
  | { type: "TOOL_CALL_OTHER" }
  | { type: "SUBAGENT"; original: string }
  | { type: "REASONING" }
  | { type: "UNRECOGNISED"; original: string }
  | { type: "MALFORMED"; reason: string };

type Fields = Record<string, unknown>;

function isObject(value: unknown): value is Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function malformed(reason: string): RunEvent {
  return { type: "MALFORMED", reason };
}

/** `fields[key]` if it is a string, else null. */
function text(fields: Fields, key: string): string | null {
  const value = fields[key];
  return isString(value) ? value : null;
}

function planSteps(value: unknown): PlanStep[] | null {
  if (!isObject(value) || !Array.isArray(value.steps)) return null;
  const steps: PlanStep[] = [];
  for (const step of value.steps) {
    if (!isObject(step) || !isString(step.id) || !isString(step.label)) return null;
    steps.push({ id: step.id, label: step.label });
  }
  return steps;
}

function custom(event: Fields): RunEvent {
  const name = text(event, "name");
  if (name === null) return malformed("CUSTOM without a name");
  const { value } = event;
  switch (name) {
    case "dd.plan": {
      const steps = planSteps(value);
      return steps === null
        ? malformed("dd.plan without a list of steps")
        : { type: "PLAN", steps };
    }
    case "dd.grounding":
    case "dd.sources": {
      if (!isObject(value) || typeof value.passed !== "boolean") {
        return malformed(`${name} without a pass or fail`);
      }
      return name === "dd.grounding"
        ? { type: "GROUNDING", report: value as unknown as GroundingReport }
        : { type: "SOURCES", report: value as unknown as SourceReport };
    }
    default:
      return { type: "UNRECOGNISED", original: `CUSTOM ${name}` };
  }
}

function finished(event: Fields): RunEvent {
  const { result, outcome } = event;
  if (isObject(outcome) && outcome.type === "cancelled") return { type: "RUN_CANCELLED" };
  if (isObject(result) && isObject(result.outcome) && isString(result.outcome.status)) {
    return { type: "RUN_FINISHED", result: result as unknown as Envelope };
  }
  return malformed("RUN_FINISHED without an envelope or a cancelled outcome");
}

/** One event from the stream, checked for the fields the reducer reads. */
export function parseEvent(raw: unknown): RunEvent {
  if (!isObject(raw) || !isString(raw.type)) return malformed("an event without a type");
  const { type } = raw;
  const need = (key: string): string | null => text(raw, key);

  switch (type) {
    case "RUN_STARTED": {
      const threadId = need("threadId");
      const runId = need("runId");
      return threadId === null || runId === null
        ? malformed("RUN_STARTED without a thread and run id")
        : { type, threadId, runId };
    }
    case "RUN_FINISHED":
      return finished(raw);
    case "RUN_ERROR": {
      const message = need("message");
      return message === null ? malformed("RUN_ERROR without a message") : { type, message };
    }
    case "CUSTOM":
      return custom(raw);
    case "STEP_STARTED":
    case "STEP_FINISHED": {
      const stepName = need("stepName");
      return stepName === null ? malformed(`${type} without a step name`) : { type, stepName };
    }
    case "TEXT_MESSAGE_START":
    case "TEXT_MESSAGE_END": {
      const messageId = need("messageId");
      return messageId === null ? malformed(`${type} without a message id`) : { type, messageId };
    }
    case "TEXT_MESSAGE_CONTENT": {
      const messageId = need("messageId");
      const delta = need("delta");
      return messageId === null || delta === null
        ? malformed("TEXT_MESSAGE_CONTENT without a message id and text")
        : { type, messageId, delta };
    }
    case "TOOL_CALL_START": {
      const toolCallId = need("toolCallId");
      if (toolCallId === null) return malformed("TOOL_CALL_START without a tool call id");
      return { type, toolCallId, toolCallName: need("toolCallName") ?? toolCallId };
    }
    case "TOOL_CALL_END": {
      const toolCallId = need("toolCallId");
      return toolCallId === null
        ? malformed("TOOL_CALL_END without a tool call id")
        : { type, toolCallId };
    }
    case "TOOL_CALL_ARGS":
    case "TOOL_CALL_RESULT":
      return { type: "TOOL_CALL_OTHER" };
    default:
      if (type.startsWith("REASONING_")) return { type: "REASONING" };
      if (type.startsWith("SUBAGENT_")) return { type: "SUBAGENT", original: type };
      return { type: "UNRECOGNISED", original: type };
  }
}
