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
  /** Whether the agent relies on this model to call tools. Absent when it does not. */
  tools?: boolean;
}

/** An Agent Skill the agent may load into its system prompt, pinned by release and digest (docs/specs/agents.md). */
export interface RawSkillUse {
  name: string;
  version: string;
  sha256: string;
}

/** The tools of one MCP server the agent calls through the harness's tool gateway (docs/specs/agents.md). */
export interface RawToolUse {
  server: string;
  tools: string[];
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
  /** The persona's icon, one emoji (docs/specs/agents.md). Absent or empty: none. */
  icon?: string;
  /** What it reads the text of attached documents for, completing "<title> reads its text …"
   * (#1326). Absent or empty: it does not read them. */
  reads_attached?: string;
  /**
   * The options a deployment's profile may set, by name (docs/specs/policy-and-identity.md).
   * Absent on an older card, which offers none.
   */
  settings?: Record<string, RawSetting>;
  /** The Agent Skills it may load (docs/specs/agents.md). Absent on an older card, which loads none. */
  skills?: RawSkillUse[];
  /** The MCP servers and tools it calls through the tool gateway (docs/specs/agents.md). Absent on an older card, which calls none. */
  tools?: RawToolUse[];
}

export interface RawSetting {
  choices: string[];
  default: string;
  description: string;
}
