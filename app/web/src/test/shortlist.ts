/** A repository shortlist for the shell's tests (`project/shortlist.ts`). */

import type { Envelope } from "../run/types";
import { SHORTLIST_CLASS } from "../project/shortlist";

export const ORDA = "r3d100012124";
export const ZENODO = "r3d100010468";

/** A shortlist as advisor.repository returns it: candidates name their record only through
 * what they rest on, and the evidence holds each cited record from the pinned export. */
export function shortlistRun(overrides: Partial<Envelope> = {}): Envelope {
  return {
    invocation_id: "0192f3a4-0000-7000-8000-00000000r3d0",
    agent_id: "advisor.repository",
    agent_version: "0.1.0",
    completed_at: "2026-11-07T12:00:00Z",
    grounding_mode: "retrieval",
    policy_bundle_ref: "profile@1",
    outcome: { status: "succeeded", statement: "Two repositories fit." },
    payload: {
      schema_class: SHORTLIST_CLASS,
      candidates: [
        {
          basis: "mandated",
          rationale: "The University asks for its own repository.",
          grounded_on: [{ source_id: ORDA, content_hash: "a".repeat(64) }],
        },
        {
          basis: "recommended",
          rationale: "A general repository that mints DataCite DOIs.",
          grounded_on: [
            { source_id: "FAIRsharing.wy4egf", content_hash: "b".repeat(64) },
            { source_id: ZENODO, content_hash: "c".repeat(64) },
          ],
        },
        { basis: "recommended", grounded_on: [{ source_id: "FAIRsharing.only", content_hash: "d".repeat(64) }] },
      ],
      not_found: [],
    },
    evidence: [
      {
        source_id: ORDA,
        snapshot_ref: "re3data:export:2026-11",
        source_uri: "https://doi.org/10.17616/R3D100012124",
        content: { re3data_id: ORDA, name: "ORDA" },
      },
      { source_id: ZENODO, snapshot_ref: "re3data:export:2026-11", content: { re3data_id: ZENODO } },
      { source_id: "FAIRsharing.wy4egf", snapshot_ref: "fairsharing:snapshot:2026-09", content: { name: "Not this" } },
    ],
    ...overrides,
  } as Envelope;
}
