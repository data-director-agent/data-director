/**
 * How the project facts panel names a fact's kind, its decision and its precision, and says what
 * a fact means in one sentence for the person deciding (docs/specs/projects.md, invariant 28).
 */

import type {
  FactKind,
  FileDecision,
  LocationPrecision,
  ProjectFact,
  SensitivityDecision,
} from "../../project/facts";

export const KIND_LABELS: Record<FactKind, string> = {
  file_inclusion: "File to deposit",
  sensitivity: "Sensitive data",
  funder: "Funder",
  required_repository: "Required repository",
  licence: "Licence",
  sharing_commitment: "Sharing commitment in the plan",
};

export const FILE_DECISION_LABELS: Record<FileDecision, string> = {
  include: "Deposit it",
  exclude: "Leave it out of the deposit",
  undecided: "A person must decide before deposit",
};

export const SENSITIVITY_LABELS: Record<SensitivityDecision, string> = {
  publish: "Publish it",
  generalise: "Publish it only generalised",
  withhold: "Do not publish it",
  undecided: "A person must decide before deposit",
};

export const PRECISION_LABELS: Record<LocationPrecision, string> = {
  exact: "Exact, as recorded",
  site: "The site or nearest named place",
  region: "A region, such as a county or national park",
  country: "The country only",
};

/** Which kinds of fact only an owner of the project may decide. */
export const OWNERS_KINDS: readonly FactKind[] = ["sensitivity", "licence"];

function fileSentence(fact: ProjectFact): string {
  const path = fact.fact_file_path ?? fact.fact_subject;
  const because = fact.fact_check_kind ? ` (${fact.fact_check_kind.replace(/_/g, " ")})` : "";
  switch (fact.file_decision) {
    case "include":
      return `Deposit ${path}${because}.`;
    case "exclude":
      return `Leave ${path} out of the deposit${because}.`;
    default:
      return `Decide whether to deposit ${path}${because}.`;
  }
}

function sensitivitySentence(fact: ProjectFact): string {
  const subject = fact.sensitive_subject ?? fact.fact_subject;
  const precision = fact.location_precision
    ? `, at this precision: ${PRECISION_LABELS[fact.location_precision].toLowerCase()}`
    : "";
  switch (fact.sensitivity_decision) {
    case "publish":
      return `Publish ${subject}${precision}.`;
    case "generalise":
      return `Publish ${subject} only generalised${precision}.`;
    case "withhold":
      return `Do not publish ${subject}.`;
    default:
      return `Decide whether ${subject} may be published, and at what precision.`;
  }
}

function commitmentSentence(fact: ProjectFact): string {
  const where = fact.commitment_repository ? ` in ${fact.commitment_repository}` : "";
  const access = fact.commitment_access ? ` with ${fact.commitment_access} access` : "";
  const licence = fact.commitment_licence ? ` under ${fact.commitment_licence}` : "";
  return `The plan commits to share ${fact.fact_subject}${where}${access}${licence}.`;
}

/** One sentence that says what `fact` decides. */
export function describeFact(fact: ProjectFact): string {
  switch (fact.fact_kind) {
    case "file_inclusion":
      return fileSentence(fact);
    case "sensitivity":
      return sensitivitySentence(fact);
    case "funder":
      return `The work was funded by ${fact.fact_funder_name ?? fact.fact_subject}.`;
    case "required_repository": {
      const by = fact.fact_required_by?.length ? `, as ${fact.fact_required_by.join(" and ")} require` : "";
      return `The data must go to ${fact.fact_repository_name ?? fact.fact_subject}${by}.`;
    }
    case "licence":
      return `Deposit the data under ${fact.licence_id ?? fact.fact_subject}.`;
    case "sharing_commitment":
      return commitmentSentence(fact);
  }
}
