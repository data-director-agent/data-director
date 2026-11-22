/**
 * A project's facts: what check agents proposed about it, and what a person decided
 * (docs/specs/projects.md, invariant 28), behind one interface so tests can stand in for the
 * server.
 *
 * An agent's proposal is never a fact. A person confirms it, changes it, or rejects it, or states
 * a fact nobody proposed; the last decision on a fact's kind and subject stands, and the harness
 * gives it to every drafter in the project. The shell sends what the person chose and never names
 * who decided: the server knows who is signed in.
 */

import { createContext, useContext } from "react";

import type { ProjectFacts } from "../api/generated/responses";
import { json } from "../http";
import type { Envelope, Problem } from "../run/types";
import { DecisionConflict } from "./api";

export type FactKind =
  | "funder"
  | "required_repository"
  | "file_inclusion"
  | "sensitivity"
  | "licence"
  | "sharing_commitment"
  | "standard"
  | "data_management_plan";
export type FileDecision = "include" | "exclude" | "undecided";
export type SensitivityDecision = "publish" | "generalise" | "withhold" | "undecided";
export type LocationPrecision = "exact" | "site" | "region" | "country";
export type StandardKind =
  | "metadata_standard"
  | "controlled_vocabulary"
  | "ontology"
  | "terminology"
  | "data_format"
  | "field_format";
export type FactVerdict = "confirmed" | "changed" | "rejected";

/**
 * The kinds a person may state with no proposal on the facts panel. A sharing commitment is not
 * one: it quotes the attached plan it was read from, so only the DMP check proposes it (#962).
 * Nor is the project's Data Management Plan: a person marks it on the Documents page (#1447).
 */
export const FACT_KINDS: readonly FactKind[] = [
  "file_inclusion",
  "sensitivity",
  "funder",
  "required_repository",
  "licence",
  "standard",
];
export const FILE_DECISIONS: readonly FileDecision[] = ["include", "exclude", "undecided"];
export const SENSITIVITY_DECISIONS: readonly SensitivityDecision[] = [
  "publish",
  "generalise",
  "withhold",
  "undecided",
];
export const PRECISIONS: readonly LocationPrecision[] = ["exact", "site", "region", "country"];
export const STANDARD_KINDS: readonly StandardKind[] = [
  "metadata_standard",
  "controlled_vocabulary",
  "ontology",
  "terminology",
  "data_format",
  "field_format",
];

/** One fact about a project, as the core contract's `ProjectFact` holds it. */
export interface ProjectFact {
  fact_kind: FactKind;
  /** The key a decision counts by within its kind. */
  fact_subject: string;
  fact_funder_name?: string;
  fact_funder_ror?: string;
  fact_crossref_funder_id?: string;
  fact_repository_name?: string;
  fact_re3data_id?: string;
  fact_required_by?: string[];
  fact_file_path?: string;
  file_decision?: FileDecision;
  fact_check_kind?: string;
  sensitive_subject?: string;
  sensitivity_decision?: SensitivityDecision;
  location_precision?: LocationPrecision;
  licence_id?: string;
  /** A sharing commitment, as the plan states it. */
  commitment_repository?: string;
  commitment_access?: string;
  commitment_licence?: string;
  /** The plan's own words, and the SHA-256 of the attached document's text they are in. */
  commitment_quote?: string;
  commitment_document?: string;
  /** A standard, vocabulary or format chosen, and what for: `dataset` or `field:<name>`. */
  standard_name?: string;
  standard_id?: string;
  standard_kind?: StandardKind;
  standard_target?: string;
  /** Which attached document is the project's Data Management Plan, by its text's SHA-256. */
  plan_document?: string;
  /** Why an agent proposed it, for the person deciding; never given to an agent. */
  proposed_because?: string;
}

export type { FactProposal, ProjectFacts } from "../api/generated/responses";

/** What a decision counts by: a fact's kind and subject, as `{kind}:{subject}`. A link to a fact
 * names it by this (`factsPath` in `route.ts`). */
export function factKey(fact: Pick<ProjectFact, "fact_kind" | "fact_subject">): string {
  return `${fact.fact_kind}:${fact.fact_subject}`;
}

function isFact(value: unknown): value is ProjectFact {
  if (typeof value !== "object" || value === null) return false;
  const fact = value as Partial<ProjectFact>;
  return typeof fact.fact_kind === "string" && typeof fact.fact_subject === "string";
}

/** The facts a run's payload proposed for a person to decide (the contract's `ProposesFacts`,
 * whichever class carries it); empty if it proposed none or did not succeed. */
export function proposedFactsOf(envelope: Envelope): ProjectFact[] {
  if (envelope.outcome.status !== "succeeded") return [];
  const proposed: unknown = envelope.payload?.proposed_facts;
  return Array.isArray(proposed) ? proposed.filter(isFact) : [];
}

export interface FactDecision {
  verdict: FactVerdict;
  proposal?: string;
  fact?: ProjectFact;
  reason?: string;
}

/**
 * The server refused a decision the person may not make: whether sensitive data may be
 * published, and the licence, are an owner's to decide (a `403`).
 */
export class FactForbidden extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "FactForbidden";
  }
}

/** The slots a fact of each kind must hold, beside its kind and subject. */
export const FACT_NEEDS: Record<FactKind, readonly (keyof ProjectFact)[]> = {
  funder: ["fact_funder_name"],
  required_repository: ["fact_repository_name"],
  file_inclusion: ["fact_file_path", "file_decision"],
  sensitivity: ["sensitive_subject", "sensitivity_decision"],
  licence: ["licence_id"],
  sharing_commitment: ["commitment_quote", "commitment_document"],
  standard: ["standard_name"],
  data_management_plan: ["plan_document"],
};

/** The slot a fact's subject is copied from, so a person names the subject once. */
export const SUBJECT_OF: Record<FactKind, keyof ProjectFact | null> = {
  funder: "fact_funder_name",
  required_repository: "fact_repository_name",
  file_inclusion: "fact_file_path",
  sensitivity: "sensitive_subject",
  licence: null,
  sharing_commitment: null,
  standard: "standard_name",
  data_management_plan: null,
};

/** The one subject a Data Management Plan fact has, so a project has at most one current plan. */
export const PLAN_SUBJECT = "project";

/** The fact that marks the attached document whose text has `digest` as the project's plan. */
export function planFact(digest: string): ProjectFact {
  return { fact_kind: "data_management_plan", fact_subject: PLAN_SUBJECT, plan_document: digest };
}

/** The slots `fact` is missing for its kind; empty when it may be sent. */
export function missingSlots(fact: ProjectFact): (keyof ProjectFact)[] {
  return FACT_NEEDS[fact.fact_kind].filter((slot) => {
    const value = fact[slot];
    return value === undefined || (typeof value === "string" && value.trim() === "");
  });
}

/** `fact` without empty values and without what only the person deciding is shown. */
export function cleaned(fact: ProjectFact): ProjectFact {
  const kept = Object.entries(fact).filter(([key, value]) => {
    if (key === "proposed_because") return false;
    if (typeof value === "string") return value.trim() !== "";
    if (Array.isArray(value)) return value.length > 0;
    return value !== undefined && value !== null;
  });
  return Object.fromEntries(kept) as unknown as ProjectFact;
}

export interface FactsApi {
  facts(projectId: string, signal?: AbortSignal): Promise<ProjectFacts>;
  decideFact(projectId: string, decision: FactDecision): Promise<ProjectFacts>;
}

const FORBIDDEN = "/project-action-forbidden";

function factsPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/facts`;
}

/** A response's body, or its error: a stale or missing proposal, or a decision not the person's. */
function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, problem) => {
    if (problem && (status === 409 || status === 404)) return new DecisionConflict(problem);
    if (problem && status === 403 && problem.type.endsWith(FORBIDDEN)) return new FactForbidden(problem);
    return null;
  });
}

export const httpFactsApi: FactsApi = {
  async facts(projectId, signal) {
    return parse(await fetch(factsPath(projectId), signal ? { signal } : {}));
  },
  async decideFact(projectId, decision) {
    return parse(
      await fetch(`${factsPath(projectId)}/decisions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(decision),
      }),
    );
  },
};

export const FactsApiContext = createContext<FactsApi>(httpFactsApi);

export function useFactsApi(): FactsApi {
  return useContext(FactsApiContext);
}
