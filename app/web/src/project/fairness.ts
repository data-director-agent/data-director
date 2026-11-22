/**
 * FAIR feedback on a project's metadata record, read from the runs whose payload is a
 * `FairnessReport` (docs/ui/fair-feedback.md, #433).
 *
 * The shell names no agent: a report is recognised by its payload's class, not by who ran it, as a
 * repository shortlist is (`./shortlist`). What it shows is the report's own: each check, whether
 * it is met, the count met of those assessed for each of F, A, I and R, and what to do next. It
 * adds no score of its own, since the checks are a short list and not a FAIRness evaluation (R4);
 * what it works out is only how one report differs from the one before.
 */

import type { Envelope } from "../run/types";
import type { ProjectDocument } from "./api";

export const FAIRNESS_CLASS = "FairnessReport";

export type Principle = "F" | "A" | "I" | "R";

/** The four principles, in the order FAIR names them, with the word a researcher reads. */
export const PRINCIPLES: readonly { id: Principle; name: string }[] = [
  { id: "F", name: "Findable" },
  { id: "A", name: "Accessible" },
  { id: "I", name: "Interoperable" },
  { id: "R", name: "Reusable" },
];

export interface FairCheck {
  /** The sub-principle it is tied to, such as `F2` or `R1.1`. */
  principle: string;
  /** The check's identifier, such as `licence-present`. */
  check: string;
  met: boolean;
  /** Left until deposit, when the repository supplies it, and not counted on a draft. */
  after_deposit?: boolean | null;
  /** Met now and not in the version a person approved last. */
  newly_met?: boolean | null;
  recommendation?: string | null;
  recommendation_derivation?: string | null;
}

export interface PrincipleTally {
  principle_group: Principle;
  tally_met: number;
  tally_assessed: number;
}

export interface VersionRef {
  document_id: string;
  version: number;
}

export interface FairnessReport {
  schema_class: typeof FAIRNESS_CLASS;
  checks: FairCheck[];
  principle_tallies: PrincipleTally[];
  /** The checks to act on first, by identifier. */
  next_steps: string[];
  assessed_version?: VersionRef | null;
  compared_with?: VersionRef | null;
  limitations: string[];
}

/** One stored report, with the run that gave it. */
export interface Assessment {
  envelope: Envelope;
  report: FairnessReport;
}

export interface Tally {
  met: number;
  assessed: number;
}

/** A payload as a FAIR report, or null when it is not one. */
export function readFairness(payload: unknown): FairnessReport | null {
  if (!payload || typeof payload !== "object") return null;
  const found = payload as Partial<FairnessReport>;
  if (found.schema_class !== FAIRNESS_CLASS || !Array.isArray(found.checks))
    return null;
  return {
    ...found,
    schema_class: FAIRNESS_CLASS,
    checks: found.checks,
    principle_tallies: Array.isArray(found.principle_tallies)
      ? found.principle_tallies
      : [],
    next_steps: Array.isArray(found.next_steps) ? found.next_steps : [],
    limitations: Array.isArray(found.limitations) ? found.limitations : [],
  };
}

/** The runs that hold a FAIR report, newest first as given, each with its report. */
export function assessments(envelopes: readonly Envelope[]): Assessment[] {
  return envelopes.flatMap((envelope) => {
    const report = readFairness(envelope.payload);
    return report ? [{ envelope, report }] : [];
  });
}

/** The principle a check counts under: the first letter of its sub-principle. */
export function principleOf(check: FairCheck): Principle | null {
  const letter = check.principle.charAt(0);
  return PRINCIPLES.some((p) => p.id === letter) ? (letter as Principle) : null;
}

/** How many checks of `principle` the report met, of those it assessed. Numbers arrive over A2A
 * as doubles (TODO(#254)), so they are rounded. */
export function tallyOf(report: FairnessReport, principle: Principle): Tally {
  const found = report.principle_tallies.find(
    (t) => t.principle_group === principle,
  );
  return found
    ? {
        met: Math.round(found.tally_met),
        assessed: Math.round(found.tally_assessed),
      }
    : { met: 0, assessed: 0 };
}

/** Every check of `principle`: those met first, then those to do, then those left until deposit. */
export function checksOf(
  report: FairnessReport,
  principle: Principle,
): FairCheck[] {
  const rank = (c: FairCheck) => (c.after_deposit ? 2 : c.met ? 0 : 1);
  return report.checks
    .filter((c) => principleOf(c) === principle)
    .sort((a, b) => rank(a) - rank(b));
}

/** The checks the report says to act on first, in its order. */
export function nextSteps(report: FairnessReport): FairCheck[] {
  return report.next_steps.flatMap((id) =>
    report.checks.filter((c) => c.check === id && !c.met),
  );
}

/** A check's identifier as words: `licence-present` reads "Licence present". */
export function checkLabel(check: FairCheck): string {
  const words = check.check.replace(/[-_]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The checks met in `latest` and not in `previous`. With no report before, those the report says
 * are newly met since the version approved last.
 */
export function newlyMet(
  latest: FairnessReport,
  previous: FairnessReport | null,
): FairCheck[] {
  if (!previous) return latest.checks.filter((c) => c.met && c.newly_met);
  const before = new Set(
    previous.checks.filter((c) => c.met).map((c) => c.check),
  );
  return latest.checks.filter((c) => c.met && !before.has(c.check));
}

/** Each principle whose count met changed between two reports, with both counts. */
export function deltas(
  latest: FairnessReport,
  previous: FairnessReport,
): { principle: Principle; before: Tally; after: Tally }[] {
  return PRINCIPLES.flatMap(({ id }) => {
    const before = tallyOf(previous, id);
    const after = tallyOf(latest, id);
    return before.met === after.met && before.assessed === after.assessed
      ? []
      : [{ principle: id, before, after }];
  });
}

/** Whether every check a draft can meet is met, so that what remains is checked at deposit. */
export function readyForDeposit(report: FairnessReport): boolean {
  const counted = report.checks.filter((c) => !c.after_deposit);
  return counted.length > 0 && counted.every((c) => c.met);
}

/** All checks met, of all assessed, across the four principles. */
export function totalOf(report: FairnessReport): Tally {
  return PRINCIPLES.reduce(
    (sum, { id }) => {
      const t = tallyOf(report, id);
      return { met: sum.met + t.met, assessed: sum.assessed + t.assessed };
    },
    { met: 0, assessed: 0 },
  );
}

/**
 * The newer version of the metadata record than the one the report assessed, or null when there is
 * none or the report does not say which it assessed.
 */
export function newerVersion(
  report: FairnessReport,
  documents: readonly ProjectDocument[],
): number | null {
  const assessed = report.assessed_version;
  if (!assessed) return null;
  const document = documents.find(
    (d) => d.document_id === assessed.document_id,
  );
  const latest = document?.versions[document.versions.length - 1];
  return latest && latest.version > assessed.version ? latest.version : null;
}

/** Whether the project holds a metadata record to assess. */
export function hasMetadataRecord(
  documents: readonly ProjectDocument[],
): boolean {
  return documents.some(
    (d) => d.document_kind === "metadata_record" && d.versions.length > 0,
  );
}

/** What the shell puts in the message box to ask for FAIR feedback, unsent. */
export const ASK_FOR_FEEDBACK =
  "How FAIR is the project's metadata record so far, and what should I improve next?";

/** What the shell puts in the message box to ask how to meet one check, unsent. */
export function askHowToMeet(check: FairCheck): string {
  const what = check.recommendation ?? checkLabel(check);
  return `How do I do this for the project's metadata record: ${what}`;
}
