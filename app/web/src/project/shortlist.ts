/**
 * The repositories an advisor shortlisted, read from its run (docs/specs/deposit.md).
 *
 * A `RepositoryOptions` payload names each candidate only through what it rests on: the
 * `grounded_on` entry whose source is a re3data record, and the evidence item citing that record
 * from a pinned re3data export. The candidate's re3data identifier and name come from there, so
 * nothing is typed by hand, and the harness resolves the rest when the researcher chooses one.
 * The shell names no agent: a shortlist is recognised by its payload's class, not by who ran it.
 */

import type { Envelope, EvidenceItem, GroundingRef } from "../run/types";

export const SHORTLIST_CLASS = "RepositoryOptions";
const RE3DATA_ID = /^r3d[0-9]{9}$/;
const RE3DATA_EXPORT = "re3data:export:";

export interface ShortlistedRepository {
  re3dataId: string;
  /** The record's name, or its identifier where the run's evidence does not hold it. */
  name: string;
  /** Where to read about it: the record's DOI or page. */
  uri: string | null;
  /** Whether a policy mandates it or the advisor recommends it. */
  basis: string | null;
  rationale: string | null;
}

function isRef(value: unknown): value is GroundingRef {
  return typeof value === "object" && value !== null && typeof (value as GroundingRef).source_id === "string";
}

/** The repositories `envelope` shortlisted, in its order; empty if it is not a shortlist. */
export function shortlistOf(envelope: Envelope): ShortlistedRepository[] {
  const payload = envelope.payload;
  if (!payload || payload.schema_class !== SHORTLIST_CLASS || !Array.isArray(payload.candidates)) return [];
  const evidence = new Map<string, EvidenceItem>();
  for (const item of envelope.evidence ?? []) {
    if (item.snapshot_ref?.startsWith(RE3DATA_EXPORT)) evidence.set(item.source_id, item);
  }
  const found: ShortlistedRepository[] = [];
  for (const candidate of payload.candidates as Record<string, unknown>[]) {
    const refs = Array.isArray(candidate.grounded_on) ? candidate.grounded_on.filter(isRef) : [];
    const re3dataId = refs.map((r) => r.source_id).find((id) => RE3DATA_ID.test(id));
    if (!re3dataId || found.some((f) => f.re3dataId === re3dataId)) continue;
    const item = evidence.get(re3dataId);
    const name = item?.content?.name;
    found.push({
      re3dataId,
      name: typeof name === "string" && name ? name : re3dataId,
      uri: item?.source_uri ?? null,
      basis: typeof candidate.basis === "string" ? candidate.basis : null,
      rationale: typeof candidate.rationale === "string" ? candidate.rationale : null,
    });
  }
  return found;
}
