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
  /** Whether re3data lists a deposit fee: `yes`, or `unstated`, since it has no value for none. */
  feeRequired: string | null;
}

/**
 * A repository named (mandated, in the data management plan or asked about) that re3data does
 * not list, such as an institution's own repository (#1334). It has no record, so it cannot be
 * chosen here and nothing is said about its terms; it is shown so that it is not lost.
 */
export interface UnlistedRepository {
  name: string;
  basis: string;
}

function isRef(value: unknown): value is GroundingRef {
  return typeof value === "object" && value !== null && typeof (value as GroundingRef).source_id === "string";
}

/** The run's evidence items from a pinned re3data export, by the record they cite. */
function re3dataEvidence(envelope: Envelope): Map<string, EvidenceItem> {
  const evidence = new Map<string, EvidenceItem>();
  for (const item of envelope.evidence ?? []) {
    if (item.snapshot_ref?.startsWith(RE3DATA_EXPORT)) evidence.set(item.source_id, item);
  }
  return evidence;
}

/** The re3data record `candidate` rests on, if any. */
function re3dataIdOf(candidate: Record<string, unknown>): string | undefined {
  const refs = Array.isArray(candidate.grounded_on) ? candidate.grounded_on.filter(isRef) : [];
  return refs.map((r) => r.source_id).find((id) => RE3DATA_ID.test(id));
}

/** One shortlisted repository: `candidate`, named from `item`, the evidence citing its record. */
function shortlisted(
  re3dataId: string,
  candidate: Record<string, unknown>,
  item: EvidenceItem | undefined,
): ShortlistedRepository {
  const name = item?.content?.name;
  return {
    re3dataId,
    name: typeof name === "string" && name ? name : re3dataId,
    uri: item?.source_uri ?? null,
    basis: typeof candidate.basis === "string" ? candidate.basis : null,
    rationale: typeof candidate.rationale === "string" ? candidate.rationale : null,
    feeRequired: typeof candidate.fee_required === "string" ? candidate.fee_required : null,
  };
}

/** The repositories `envelope` shortlisted, in its order; empty if it is not a shortlist. */
export function shortlistOf(envelope: Envelope): ShortlistedRepository[] {
  const payload = envelope.payload;
  if (!payload || payload.schema_class !== SHORTLIST_CLASS || !Array.isArray(payload.candidates)) return [];
  const evidence = re3dataEvidence(envelope);
  const found: ShortlistedRepository[] = [];
  for (const candidate of payload.candidates as Record<string, unknown>[]) {
    const re3dataId = re3dataIdOf(candidate);
    if (!re3dataId || found.some((f) => f.re3dataId === re3dataId)) continue;
    found.push(shortlisted(re3dataId, candidate, evidence.get(re3dataId)));
  }
  return found;
}

/** The repositories named that re3data does not list, in the run's order; empty if none. */
export function unlistedOf(envelope: Envelope): UnlistedRepository[] {
  const payload = envelope.payload;
  if (!payload || payload.schema_class !== SHORTLIST_CLASS || !Array.isArray(payload.unlisted)) return [];
  return (payload.unlisted as Record<string, unknown>[]).flatMap((entry) =>
    typeof entry.name === "string" && typeof entry.basis === "string" ? [{ name: entry.name, basis: entry.basis }] : [],
  );
}
