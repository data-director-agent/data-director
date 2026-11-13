/**
 * What the run endpoints return (app/src/dd_app/app.py), as the shell reads it.
 *
 * The envelope is the contract's (sdk/src/dd_sdk/contract/models.py), typed in
 * `@data-director/agent-view`. These types cover the fields the shell uses; a field it does not
 * know is ignored, not refused.
 *
 * TODO(#69): generate these from the contract's JSON Schema, and replace the one-shot run
 * with the AG-UI event stream.
 */

import type { Envelope, OutcomeStatus } from "@data-director/agent-view";

export type {
  Envelope,
  EvidenceItem,
  GroundingRef,
  ModelAccount,
  ModelCall,
  Outcome,
  OutcomeStatus,
  Problem,
} from "@data-director/agent-view";

/** A check's stored summary; null if the run's directory holds none. */
export interface CheckReport {
  passed: boolean;
  summary: string;
}

export interface Checks {
  grounding: CheckReport | null;
  sources: CheckReport | null;
}

export interface RunResult {
  envelope: Envelope;
  checks: Checks;
}

export interface RunRow {
  invocation_id: string;
  agent_id: string;
  status: OutcomeStatus;
  completed_at: string;
  acting_for: string | null;
}

export interface Example {
  name: string;
  schema_class: string | null;
  input: Record<string, unknown>;
}
