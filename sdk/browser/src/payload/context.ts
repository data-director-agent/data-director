/** What every part of a payload's layout needs: the schema, the derivations and the evidence. */

import type { Derivation } from "../spec/read";
import type { JsonSchema } from "../schema/shape";
import { evidenceKey } from "./evidence";
import type { EvidenceItem } from "./types";

export interface Context {
  root: JsonSchema;
  derivations: Map<string, Derivation>;
  evidence: Map<string, { index: number; name: string }>;
  idPrefix: string;
}

export function makeContext(
  root: JsonSchema,
  derivations: Derivation[],
  evidence: EvidenceItem[],
  idPrefix: string,
): Context {
  return {
    root,
    derivations: new Map(derivations.map((d) => [d.path, d])),
    evidence: new Map(
      evidence.map((item, index) => [
        evidenceKey(item),
        { index, name: typeof item.content?.name === "string" ? item.content.name : item.source_id },
      ]),
    ),
    idPrefix,
  };
}

export function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || (Array.isArray(value) && value.length === 0);
}

/** The fields at `prefix` that only record how a sibling was derived. */
export function recorders(ctx: Context, prefix: string): Set<string> {
  const names = new Set<string>();
  for (const d of ctx.derivations.values()) {
    if (d.recordedIn && d.path.startsWith(prefix) && !d.path.slice(prefix.length).includes(".")) {
      names.add(d.recordedIn);
    }
  }
  return names;
}
