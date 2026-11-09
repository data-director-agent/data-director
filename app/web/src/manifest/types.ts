/**
 * What `GET /api/agents` returns (app/src/dd_app/governance.py), as the shell reads it.
 *
 * Each manifest entry is the agent card's `agent-spec/v0` extension (`describe()` in
 * sdk/src/dd_sdk/agent.py, typed in `@data-director/agent-view` as `RawAgentSpec`) beside what
 * the deployment's profile assigns it. A field the shell does not know is ignored, not refused.
 *
 * TODO(#67): generate these from the extension's JSON Schema once the oversight extension has one
 * (increment 2, #67).
 */

import type { RawAgentSpec } from "@data-director/agent-view";

export type {
  DerivationHow,
  GroundingMode,
  RawDerived,
  RawModelUse,
} from "@data-director/agent-view";

export interface RawManifestEntry extends RawAgentSpec {
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
