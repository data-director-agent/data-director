/**
 * The parts of the contract's envelope (sdk/src/dd_sdk/contract/models.py) that a payload is read
 * with. These types cover the fields a page uses; a field they do not know is ignored, not refused.
 *
 * TODO(#69): generate these from the contract's JSON Schema.
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

/** Whose account paid for a model call: a person's own or the deployment's, never whose. */
export type ModelAccount = "own" | "deployment";

/** One call an agent made to a language model. The prompt is named by digest, never included. */
export interface ModelCall {
  model_provider: string;
  model_id: string;
  called_at: string;
  prompt_digest: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  /** Absent in runs recorded before contract 0.10.0. */
  model_account?: ModelAccount | null;
}

export interface Telemetry {
  model_calls?: ModelCall[] | null;
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
  telemetry?: Telemetry | null;
}
