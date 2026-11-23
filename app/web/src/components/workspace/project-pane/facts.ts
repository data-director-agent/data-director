/**
 * What the pane reads of a project's facts: the facts read for the open project (read again after
 * each turn), the proposals grouped by kind, and a fact's value in a few words. Kinds are named and
 * facts described as the project facts panel does (`../../project/factWording`).
 */

import type {
  FactKind,
  FactProposal,
  ProjectFact,
  ProjectFacts,
} from "../../../project/facts";
import { useFactsApi } from "../../../project/facts";
import { type Resource, useResource } from "../../../useResource";
import { describeFact } from "../../project/factWording";

/** The kinds that shape what Data Director says, in the order the pane lists them. */
export const WORKING_KINDS: readonly FactKind[] = [
  "field_of_study",
  "funder",
  "required_repository",
  "sensitivity",
  "licence",
  "sharing_commitment",
  "standard",
  "data_description",
];

/** A fact's value in a few words where its kind has one; otherwise its sentence. */
export function factValue(fact: ProjectFact): string {
  switch (fact.fact_kind) {
    case "funder":
      return fact.fact_funder_name ?? fact.fact_subject;
    case "required_repository":
      return fact.fact_repository_name ?? fact.fact_subject;
    case "licence":
      return fact.licence_id ?? fact.fact_subject;
    case "standard":
      return fact.standard_name ?? fact.fact_subject;
    case "field_of_study":
      return fact.field_name ?? fact.fact_subject;
    default:
      return describeFact(fact);
  }
}

/** The proposals waiting for a decision, one group per kind, in the order they were proposed. */
export function proposalsByKind(
  proposals: readonly FactProposal[],
): [FactKind, FactProposal[]][] {
  const groups = new Map<FactKind, FactProposal[]>();
  for (const p of proposals) {
    const kind = p.fact.fact_kind;
    groups.set(kind, [...(groups.get(kind) ?? []), p]);
  }
  return [...groups.entries()];
}

/** The open project's facts, read again whenever `refresh` changes (a turn has settled). */
export function useProjectFacts(
  projectId: string | null,
  refresh: unknown,
): Resource<ProjectFacts> {
  const factsApi = useFactsApi();
  return useResource(
    projectId,
    (id, signal) => factsApi.facts(id, signal),
    refresh,
  ).resource;
}
