/**
 * An agent's specification as the `agent-spec/v0` extension carries it: `describe(spec)` in
 * sdk/src/dd_sdk/agent.py, in the contract's snake_case. The harness's manifest is a list of
 * these, and the app's `GET /api/agents` adds what the deployment's profile assigns to each.
 *
 * TODO(#67): generate these from the extension's JSON Schema once it has one.
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

export interface RawSchemaEntry {
  digest: string;
  json_schema: unknown;
  /** The class's SHACL shapes, when the card carries them. */
  shapes?: unknown;
}

export interface RawAgentSpec {
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
  schemas: Record<string, RawSchemaEntry>;
  /** The process flow step ids it serves (docs/specs/orchestration.md). Absent on an older card. */
  serves?: string[];
  /** The persona's name as a researcher sees it (docs/specs/agents.md). Absent or empty: none. */
  title?: string;
}
