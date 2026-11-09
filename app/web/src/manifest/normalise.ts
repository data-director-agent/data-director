/**
 * The manifest as the shell draws it: one `AgentView` per agent, which is the agent's
 * specification as `@data-director/agent-view` reads it, with what this deployment's policy gate
 * will do with it.
 *
 * A field an agent has not declared becomes `{ state: "undeclared" }`, never a default, so the
 * page can say "Not declared" rather than imply a limit or a reliability nobody claimed.
 */

import { type AgentSpec, specFromRaw } from "@data-director/agent-view";

import type { RawAgentsResponse, RawManifestEntry } from "./types";

export { agentName, type Derivation } from "@data-director/agent-view";

export type Declared<T> = { state: "declared"; value: T } | { state: "undeclared" };

/** What the deployment's policy gate will do with a run of this agent (docs/specs/policy-and-identity.md). */
export type GateStatus =
  | { kind: "permitted"; actionClass: string }
  | { kind: "needs-approval"; actionClass: string }
  | { kind: "not-permitted" }
  | { kind: "mismatch"; declared: string; assigned: string };

/** The oversight declaration (#67). Its fields are undeclared until an agent sends one. */
export interface Oversight {
  actions: Declared<unknown>;
  limits: Declared<unknown>;
  reliability: Declared<unknown>;
  outcomes: Declared<unknown>;
  dataSensitivity: Declared<unknown>;
}

export interface AgentView extends AgentSpec {
  gate: GateStatus;
  oversight: Oversight;
}

export interface Unregistered {
  name: string;
  state: "unavailable" | "incompatible";
  reason: string;
}

export interface Directory {
  agents: AgentView[];
  unregistered: Unregistered[];
  profileRef: string;
  /** The agent the profile names for the conversation, or null when it names none. */
  orchestratorId: string | null;
  actingFor: { name: string; assurance: string; vouchedBy?: string };
}

const UNDECLARED = { state: "undeclared" } as const;

export function gateStatus(entry: RawManifestEntry): GateStatus {
  const assigned = entry.assigned_action_class;
  if (assigned === null) return { kind: "not-permitted" };
  if (assigned !== entry.action_class) {
    return { kind: "mismatch", declared: entry.action_class, assigned };
  }
  return entry.requires_approval
    ? { kind: "needs-approval", actionClass: assigned }
    : { kind: "permitted", actionClass: assigned };
}

export function normaliseAgent(entry: RawManifestEntry): AgentView {
  return {
    ...specFromRaw(entry),
    gate: gateStatus(entry),
    // No agent carries the oversight extension yet (increment 2).
    oversight: {
      actions: UNDECLARED,
      limits: UNDECLARED,
      reliability: UNDECLARED,
      outcomes: UNDECLARED,
      dataSensitivity: UNDECLARED,
    },
  };
}

export function normalise(response: RawAgentsResponse): Directory {
  return {
    agents: response.agents.map(normaliseAgent),
    unregistered: [
      ...Object.entries(response.unavailable ?? {}).map(([name, reason]) => ({
        name,
        state: "unavailable" as const,
        reason,
      })),
      ...Object.entries(response.incompatible ?? {}).map(([name, reason]) => ({
        name,
        state: "incompatible" as const,
        reason,
      })),
    ],
    profileRef: response.profile.ref,
    orchestratorId: response.profile.orchestrator ?? null,
    actingFor: {
      name: response.acting_for.name,
      assurance: response.acting_for.assurance,
      ...(response.acting_for.vouched_by ? { vouchedBy: response.acting_for.vouched_by } : {}),
    },
  };
}
