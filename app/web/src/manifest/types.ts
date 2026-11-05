/**
 * What `GET /api/agents` returns (app/src/dd_app/governance.py), as the shell reads it.
 *
 * Each manifest entry is the agent card's `agent-spec/v0` extension (`describe()` in
 * sdk/src/dd_sdk/agent.py) beside what the deployment's profile assigns it. These types cover
 * the fields the shell uses; a field it does not know is ignored, not refused.
 *
 * TODO(#67): generate these from the extension's JSON Schema once the oversight extension has one
 * (increment 2, #67).
 */

export type GroundingMode = "retrieval" | "input_only" | "none" | "delegation";
export type DerivationHow = "template" | "model" | "lexical" | "registry";

export interface RawDerived {
  how: DerivationHow;
  recorded_in?: string | null;
}

/** A model the agent sends data to, as configured (docs/specs/policy-and-identity.md). It names no credential. */
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
  /** Absent on a card written before docs/specs/policy-and-identity.md, which declares no model. */
  models?: RawModelUse[];
  schemas: Record<string, { digest: string; json_schema: unknown }>;
  /** The process flow step ids it serves (docs/specs/orchestration.md). Absent on an older card. */
  serves?: string[];
  /** The persona's name as a researcher sees it (docs/specs/agents.md). Absent or empty: none. */
  title?: string;
  assigned_action_class: string | null;
  requires_approval: boolean;
  /** The oversight extension (#67). No card carries it yet. */
  oversight?: unknown;
}

export interface RawAgentsResponse {
  agents: RawManifestEntry[];
  unavailable: Record<string, string>;
  incompatible: Record<string, string>;
  /** `orchestrator` is the agent the profile names for the conversation (docs/specs/app.md). Absent
   * from a server older than the key; null when the profile names none. */
  profile: { ref: string; digest: string; orchestrator?: string | null };
  acting_for: { name: string; assurance: string; vouched_by?: string };
}
