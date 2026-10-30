/**
 * The manifest as the shell draws it: one `AgentView` per agent.
 *
 * A field an agent has not declared becomes `{ state: "undeclared" }`, never a default, so the
 * page can say "Not declared" rather than imply a limit or a reliability nobody claimed.
 */

import type { JsonSchema } from "../run/schema";
import type {
  DerivationHow,
  GroundingMode,
  RawAgentsResponse,
  RawManifestEntry,
  RawModelUse,
} from "./types";

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
  /** The sibling field that records how each value was produced, if it varies by value. */
  recordedIn?: string;
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
  /** The persona's name as a researcher sees it (ADR-0033). Empty: the card names none. */
  title: string;
  version: string;
  description: string;
  contractVersion: string;
  accepts: string[];
  payload: string | null;
  /** Each input and payload class's JSON Schema, by class name. */
  schemas: Record<string, JsonSchema>;
  groundingMode: GroundingMode;
  derivations: Derivation[];
  declaredActionClass: string;
  gate: GateStatus;
  /** The models it sends data to. Empty: it calls none (see `modelsDeclared`). */
  models: RawModelUse[];
  /** False for a card with no `models` key: nothing is known about whether it uses a model. */
  modelsDeclared: boolean;
  /** The process flow steps it serves, which place it in the flow. Empty: none. */
  serves: string[];
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

/** What to call the agent in prose: its persona title, or its id when it has none. */
export function agentName(agent: Pick<AgentView, "id" | "title">): string {
  return agent.title || agent.id;
}

export function normaliseAgent(entry: RawManifestEntry): AgentView {
  return {
    id: entry.agent_id,
    title: entry.title ?? "",
    version: entry.version,
    description: entry.description,
    contractVersion: entry.contract_version,
    accepts: [...entry.accepts],
    payload: entry.payload,
    schemas: Object.fromEntries(
      Object.entries(entry.schemas ?? {}).map(([name, s]) => [name, s.json_schema as JsonSchema]),
    ),
    groundingMode: entry.grounding_mode,
    derivations: Object.entries(entry.derivations ?? {})
      .map(([path, d]): Derivation =>
        d.recorded_in ? { path, how: d.how, recordedIn: d.recorded_in } : { path, how: d.how },
      )
      .sort((a, b) => a.path.localeCompare(b.path)),
    declaredActionClass: entry.action_class,
    gate: gateStatus(entry),
    models: (entry.models ?? []).map((m) => ({ ...m })),
    modelsDeclared: entry.models !== undefined,
    serves: [...(entry.serves ?? [])],
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
