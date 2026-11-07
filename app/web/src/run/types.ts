/**
 * What the run endpoints return (app/src/dd_app/app.py), as the shell reads it.
 *
 * The envelope is the contract's (sdk/src/dd_sdk/contract/models.py). These types cover the
 * fields the shell uses; a field it does not know is ignored, not refused.
 *
 * TODO(#68, #69): generate these from the contract's JSON Schema, and replace the one-shot run
 * with the AG-UI event stream.
 */

export type OutcomeStatus = "succeeded" | "abstained" | "referred" | "failed" | "suspended";

export interface Outcome {
  status: OutcomeStatus;
  reason_code?: string | null;
  referred_to?: string | null;
  statement: string;
}

export interface Problem {
  type: string;
  title: string;
  detail?: string | null;
  http_status?: number | null;
}

export interface GroundingRef {
  source_id: string;
  content_hash: string;
}

export interface EvidenceItem {
  source_id: string;
  source_uri?: string | null;
  retrieved_at?: string | null;
  snapshot_ref?: string | null;
  content_hash?: string | null;
  content?: Record<string, unknown> | null;
}

export interface Envelope {
  invocation_id: string;
  agent_id: string;
  agent_version: string;
  completed_at: string;
  grounding_mode: string;
  policy_bundle_ref: string;
  acting_for?: { name: string; assurance?: string } | null;
  outcome: Outcome;
  payload?: Record<string, unknown> | null;
  evidence?: EvidenceItem[] | null;
  problem?: Problem | null;
  requires_human_review?: boolean;
}

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
