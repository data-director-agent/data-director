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
