/**
 * The manifest as the shell draws it: one `AgentView` per agent.
 *
 * A field an agent has not declared becomes `{ state: "undeclared" }`, never a default, so the
 * page can say "Not declared" rather than imply a limit or a reliability nobody claimed.
 */

import type { DerivationHow, GroundingMode, RawAgentsResponse, RawManifestEntry } from "./types";

export type Declared<T> = { state: "declared"; value: T } | { state: "undeclared" };

/** What the deployment's policy gate will do with a run of this agent (ADR-0017). */
export type GateStatus =
  | { kind: "permitted"; actionClass: string }
  | { kind: "needs-approval"; actionClass: string }
  | { kind: "not-permitted" }
  | { kind: "mismatch"; declared: string; assigned: string };

export interface Derivation {
  path: string;
  how: DerivationHow;
}

/** The oversight declaration (ADR-0025). Its fields are undeclared until an agent sends one. */
export interface Oversight {
  actions: Declared<unknown>;
  limits: Declared<unknown>;
  reliability: Declared<unknown>;
  outcomes: Declared<unknown>;
  dataSensitivity: Declared<unknown>;
}

export interface AgentView {
  id: string;
  version: string;
  description: string;
  contractVersion: string;
  accepts: string[];
  payload: string | null;
  groundingMode: GroundingMode;
  derivations: Derivation[];
  declaredActionClass: string;
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
  actingFor: { name: string; assurance: string };
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
    id: entry.agent_id,
    version: entry.version,
    description: entry.description,
    contractVersion: entry.contract_version,
    accepts: [...entry.accepts],
    payload: entry.payload,
    groundingMode: entry.grounding_mode,
    derivations: Object.entries(entry.derivations ?? {})
      .map(([path, d]) => ({ path, how: d.how }))
      .sort((a, b) => a.path.localeCompare(b.path)),
    declaredActionClass: entry.action_class,
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
    actingFor: response.acting_for,
  };
}
