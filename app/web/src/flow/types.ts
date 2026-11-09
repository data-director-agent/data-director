/**
 * What `GET /api/process-flow` returns: the Blueprint's entry points and phases (§8.1, §8.2),
 * serialised from `dd_sdk.process_flow` so the shell keeps no copy of its own.
 */

export interface FlowStep {
  /** A stable label, `<phase>.<step>`, that an agent's `serves` names (docs/specs/orchestration.md). */
  id: string;
  /** The Blueprint's wording, for the orchestrator; the shell shows `label`. */
  text: string;
  /** The step in a researcher's words. */
  label: string;
  /** The Blueprint requirements applied at this step; empty when the figure names none. */
  requirements: string[];
  optional: boolean;
  /** The Blueprint has the step but this project does not yet do it: shown, and said so. */
  out_of_scope: boolean;
}

export interface FlowPhase {
  number: number;
  /** The Blueprint's title; the shell shows `name`. */
  title: string;
  /** A short name for the phase in a researcher's words. */
  name: string;
  /** One sentence on what the phase is for. */
  summary: string;
  steps: FlowStep[];
}

export interface FlowEntry {
  number: number;
  text: string;
  /** The phase a researcher entering here joins at. */
  starts_at: number;
}

export interface ProcessFlow {
  entries: FlowEntry[];
  phases: FlowPhase[];
}

/** How far a step has gone, as the project log shows it; a step the server leaves out is open. */
export type StepState = "started" | "done" | "skipped";

/** What a researcher may mark a step; "open" withdraws an earlier mark. */
export type StepMark = "done" | "skipped" | "open";

/**
 * Where a project is in the flow, derived by the harness from the project log on every read and
 * never stored (docs/specs/orchestration.md): the entry point the researcher chose, each step
 * started, done or skipped, and the step to suggest next. The suggestion is never a gate.
 */
export interface ProjectProgress {
  entry: number | null;
  /** Who recorded the entry point: the researcher, or Data Director from what they said. */
  entry_source?: "researcher" | "model" | null;
  steps: Record<string, StepState>;
  suggested: string | null;
}
