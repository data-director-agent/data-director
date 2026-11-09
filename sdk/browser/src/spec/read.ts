/**
 * An agent's specification as a page draws it: camelCase, derivations as a sorted list, and each
 * class's JSON Schema by class name. Nothing here names an agent class: everything is read from
 * the specification itself.
 */

import { isRecord } from "../card/read";
import type { JsonSchema } from "../schema/shape";
import type { DerivationHow, GroundingMode, RawAgentSpec, RawModelUse } from "./types";

export interface Derivation {
  path: string;
  how: DerivationHow;
  /** The sibling field that records how each value was produced, if it varies by value. */
  recordedIn?: string;
}

export interface AgentSpec {
  id: string;
  /** The persona's name as a researcher sees it (docs/specs/agents.md). Empty: the card names none. */
  title: string;
  version: string;
  description: string;
  contractVersion: string;
  accepts: string[];
  payload: string | null;
  /** Each input and payload class's JSON Schema, by class name. */
  schemas: Record<string, JsonSchema>;
  /** Each class's schema digest, by class name. */
  digests: Record<string, string>;
  groundingMode: GroundingMode;
  derivations: Derivation[];
  declaredActionClass: string;
  /** The models it sends data to. Empty: it calls none (see `modelsDeclared`). */
  models: RawModelUse[];
  /** False for a card with no `models` key: nothing is known about whether it uses a model. */
  modelsDeclared: boolean;
  /** The process flow steps it serves, which place it in the flow. Empty: none. */
  serves: string[];
}

/** What to call the agent in prose: its persona title, or its id when it has none. */
export function agentName(agent: Pick<AgentSpec, "id" | "title">): string {
  return agent.title || agent.id;
}

export function specFromRaw(raw: RawAgentSpec): AgentSpec {
  const schemas = Object.entries(raw.schemas ?? {});
  return {
    id: raw.agent_id,
    title: raw.title ?? "",
    version: raw.version,
    description: raw.description,
    contractVersion: raw.contract_version,
    accepts: [...raw.accepts],
    payload: raw.payload,
    schemas: Object.fromEntries(schemas.map(([name, s]) => [name, s.json_schema as JsonSchema])),
    digests: Object.fromEntries(schemas.map(([name, s]) => [name, s.digest])),
    groundingMode: raw.grounding_mode,
    derivations: Object.entries(raw.derivations ?? {})
      .map(([path, d]): Derivation =>
        d.recorded_in ? { path, how: d.how, recordedIn: d.recorded_in } : { path, how: d.how },
      )
      .sort((a, b) => a.path.localeCompare(b.path)),
    declaredActionClass: raw.action_class,
    models: (raw.models ?? []).map((m) => ({ ...m })),
    modelsDeclared: raw.models !== undefined,
    serves: [...(raw.serves ?? [])],
  };
}

const REQUIRED_TEXT = ["agent_id", "version", "description", "action_class", "grounding_mode"];

/**
 * `specFromRaw` for a value that arrived as JSON: null if it lacks the fields every specification
 * has. Optional parts of the wrong shape are dropped rather than refused.
 */
export function readAgentSpec(value: unknown): AgentSpec | null {
  if (!isRecord(value) || !REQUIRED_TEXT.every((k) => typeof value[k] === "string")) return null;
  const list = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === "string") : []);
  const record = (v: unknown) => (isRecord(v) ? v : {});
  const schemas = Object.fromEntries(
    Object.entries(record(value.schemas)).filter(([, s]) => isRecord(s) && isRecord(s.json_schema)),
  );
  const derivations = Object.fromEntries(
    Object.entries(record(value.derivations)).filter(([, d]) => isRecord(d) && typeof d.how === "string"),
  );
  return specFromRaw({
    ...(value as unknown as RawAgentSpec),
    accepts: list(value.accepts),
    payload: typeof value.payload === "string" ? value.payload : null,
    contract_version: typeof value.contract_version === "string" ? value.contract_version : "",
    schemas: schemas as RawAgentSpec["schemas"],
    derivations: derivations as RawAgentSpec["derivations"],
    ...(Array.isArray(value.models) ? { models: value.models.filter(isRecord) as unknown as RawModelUse[] } : {}),
    ...(Array.isArray(value.serves) ? { serves: list(value.serves) } : {}),
    ...(typeof value.title === "string" ? { title: value.title } : {}),
  });
}
