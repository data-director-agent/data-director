/**
 * What `GET /api/agents` returns (app/src/dd_app/governance.py), as the shell reads it.
 *
 * Each manifest entry is the agent card's `agent-spec/v0` extension (`describe()` in
 * sdk/src/dd_sdk/agent.py) beside what the deployment's profile assigns it. These types cover
 * the fields the shell uses; a field it does not know is ignored, not refused.
 *
 * TODO: generate these from the extension's JSON Schema once the oversight extension has one
 * (increment 2, ADR-0025).
 */

export type GroundingMode = "retrieval" | "input_only" | "none" | "delegation";
export type DerivationHow = "template" | "model" | "lexical" | "registry";

export interface RawDerived {
  how: DerivationHow;
  recorded_in?: string | null;
}

/** A model the agent sends data to, as configured (ADR-0026). It names no credential. */
export interface RawModelUse {
  provider: string;
  model: string;
  hosting: "hosted" | "local";
}

export interface RawManifestEntry {
  agent_id: string;
  version: string;
  description: string;
  action_class: string;
  accepts: string[];
  grounding_mode: GroundingMode;
  payload: string | null;
  derivations: Record<string, RawDerived>;
  contract_version: string;
  /** Absent on a card written before ADR-0026, which declares no model. */
  models?: RawModelUse[];
  schemas: Record<string, { digest: string; json_schema: unknown }>;
  assigned_action_class: string | null;
  requires_approval: boolean;
  /** The oversight extension (ADR-0025). No card carries it yet. */
  oversight?: unknown;
}

export interface RawAgentsResponse {
  agents: RawManifestEntry[];
  unavailable: Record<string, string>;
  incompatible: Record<string, string>;
  /** `orchestrator` is the agent the profile names for the conversation (ADR-0024 §10). Absent
   * from a server older than the key; null when the profile names none. */
  profile: { ref: string; digest: string; orchestrator?: string | null };
  acting_for: { name: string; assurance: string };
}
