/**
 * The Data Director's A2A extensions, read from a card.
 *
 * - `agent-spec/v0`, on every agent's card: the agent's `describe(spec)` (sdk/src/dd_sdk/agent.py,
 *   `EXTENSION_URI` in sdk/src/dd_sdk/wire.py).
 * - `manifest/v0`, on the harness's card: `{agents: [describe(spec), …]}`, one per registered agent
 *   (harness/src/dd_harness/transport/a2a.py).
 *
 * TODO(#3): the URIs are not yet registered persistent identifiers.
 */

import { type AgentSpec, readAgentSpec } from "../spec/read";
import type { AgentCard, AgentExtension } from "./types";

export const AGENT_SPEC_URI = "https://w3id.org/data-director/a2a/agent-spec/v0";
export const MANIFEST_URI = "https://w3id.org/data-director/a2a/manifest/v0";

export function extensionsOf(card: AgentCard): AgentExtension[] {
  return card.capabilities?.extensions ?? [];
}

export function findExtension(card: AgentCard, uri: string): AgentExtension | undefined {
  return extensionsOf(card).find((x) => x.uri === uri);
}

/** The agent's specification, from its `agent-spec/v0` extension; null if it has none. */
export function agentSpecOf(card: AgentCard): AgentSpec | null {
  const params = findExtension(card, AGENT_SPEC_URI)?.params;
  return params ? readAgentSpec(params) : null;
}

/** Each agent a harness may invoke, from its `manifest/v0` extension; null if it has none. */
export function manifestOf(card: AgentCard): AgentSpec[] | null {
  const params = findExtension(card, MANIFEST_URI)?.params;
  if (!params || !Array.isArray(params.agents)) return null;
  return params.agents.map(readAgentSpec).filter((s): s is AgentSpec => s !== null);
}
