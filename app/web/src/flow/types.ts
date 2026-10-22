/**
 * What `GET /api/process-flow` returns: the Blueprint's entry points and phases (§8.1, §8.2),
 * serialised from `dd_sdk.process_flow` so the shell keeps no copy of its own.
 */

export interface FlowStep {
  text: string;
  /** The Blueprint requirements applied at this step; empty when the figure names none. */
  requirements: string[];
  optional: boolean;
}

export interface FlowPhase {
  number: number;
  title: string;
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
