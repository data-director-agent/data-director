/**
 * What `GET /api/process-flow` returns: the Blueprint's entry points and phases (§8.1, §8.2),
 * serialised from `dd_sdk.process_flow` so the shell keeps no copy of its own, and where a
 * project is in that flow. The server's types are generated
 * (`../api/generated/responses.ts`).
 */

export type {
  Decision,
  FlowEntry,
  FlowPhase,
  FlowStep,
  ProcessFlow,
  ProjectProgress,
  StepReason,
  StepState,
} from "../api/generated/responses";

/** What a researcher may mark a step; "open" withdraws an earlier mark. */
export type StepMark = "done" | "skipped" | "open";
