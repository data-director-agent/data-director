/**
 * The repositories an advisor shortlisted, read from its run (docs/specs/deposit.md).
 *
 * A `RepositoryOptions` payload names each candidate only through what it rests on: its first
 * `grounded_on` entry, a registry's record, and the evidence item citing that record from a
 * pinned re3data export or, for a repository re3data does not list, DataCite snapshot. The
 * candidate's identifier and name come from there, so nothing is typed by hand, and the harness
 * resolves the rest when the researcher chooses one.
 * The shell names no agent: a shortlist is recognised by its payload's class, not by who ran it.
 */

import type { Envelope, EvidenceItem, GroundingRef } from "../run/types";

export const SHORTLIST_CLASS = "RepositoryOptions";
const REPOSITORY_ID = /^(r3d[0-9]{9}|[a-z0-9]+\.[a-z0-9.-]+)$/;
const REGISTRY_COPIES = ["re3data:export:", "datacite:repositories:"];

export interface ShortlistedRepository {
  /** Its re3data identifier, or, for one re3data does not list, its DataCite one. */
  repositoryId: string;
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
 * A repository named (mandated, in the data management plan or asked about) that neither re3data
 * nor DataCite lists, such as a local archive that mints no DataCite DOIs (#1334, #1342). It has no
 * record, so it cannot be chosen here and nothing is said about its terms; it is shown so that it
 * is not lost.
 */
export interface UnlistedRepository {
  name: string;
  basis: string;
}

function isRef(value: unknown): value is GroundingRef {
  return typeof value === "object" && value !== null && typeof (value as GroundingRef).source_id === "string";
}

/** The run's evidence items from a pinned registry, by the record they cite. */
function registryEvidence(envelope: Envelope): Map<string, EvidenceItem> {
  const evidence = new Map<string, EvidenceItem>();
  for (const item of envelope.evidence ?? []) {
    const ref = item.snapshot_ref ?? "";
    if (REGISTRY_COPIES.some((copy) => ref.startsWith(copy))) evidence.set(item.source_id, item);
  }
  return evidence;
}

/** The registry record `candidate` rests on, if any: its first grounding, by which it is named. */
function repositoryIdOf(candidate: Record<string, unknown>): string | undefined {
  const refs = Array.isArray(candidate.grounded_on) ? candidate.grounded_on.filter(isRef) : [];
  return refs.map((r) => r.source_id).find((id) => REPOSITORY_ID.test(id));
}

/** One shortlisted repository: `candidate`, named from `item`, the evidence citing its record. */
function shortlisted(
  repositoryId: string,
  candidate: Record<string, unknown>,
  item: EvidenceItem | undefined,
): ShortlistedRepository {
  const name = item?.content?.name;
  return {
    repositoryId,
    name: typeof name === "string" && name ? name : repositoryId,
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
  const evidence = registryEvidence(envelope);
  const found: ShortlistedRepository[] = [];
  for (const candidate of payload.candidates as Record<string, unknown>[]) {
    const repositoryId = repositoryIdOf(candidate);
    if (!repositoryId || found.some((f) => f.repositoryId === repositoryId)) continue;
    found.push(shortlisted(repositoryId, candidate, evidence.get(repositoryId)));
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
