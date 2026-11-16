/**
 * What the run endpoints return (app/src/dd_app/app.py), as the shell reads it.
 *
 * The envelope is the contract's (sdk/src/dd_sdk/contract/models.py), typed in
 * `@data-director/agent-view`. These types cover the fields the shell uses; a field it does not
 * know is ignored, not refused.
 *
 * TODO(#69): generate these from the contract's JSON Schema. The run's AG-UI event stream is
 * read by `reduce.ts` (#947); the one-shot turn goes when the run view draws from that stream
 * (#949).
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

/**
 * The grounding check's report, as the harness's AG-UI binding sends it in `CUSTOM dd.grounding`
 * (`GroundingReport`, harness/src/dd_harness/grounding.py).
 */
export interface GroundingReport {
  passed: boolean;
  mode?: string | null;
  violations?: string[];
  retrieval_count?: number;
  chat_count?: number;
}

/**
 * The source check's report, as sent in `CUSTOM dd.sources` (`SourceReport`,
 * harness/src/dd_harness/sources.py).
 */
export interface SourceReport {
  passed: boolean;
  verified?: number;
  unresolved?: string[];
  violations?: string[];
}
