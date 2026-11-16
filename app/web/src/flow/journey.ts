/**
 * The journey map's shape (docs/specs/app.md, "The journey map"): the process flow joined to a
 * project's progress, phase by phase, with each step's state and the word that decided it, the
 * intake's decision points placed before their steps, and the entry points on the phases they
 * start at. It computes no state and no suggestion: those are the harness's, read from
 * `ProjectProgress`. What it adds is only arrangement, and which steps wait on the researcher,
 * read from the documents awaiting their decision and the decisions not yet answered.
 */

import type { ProjectDocument } from "../project/api";
import type {
  Decision,
  FlowEntry,
  FlowPhase,
  FlowStep,
  ProcessFlow,
  ProjectProgress,
  StepReason,
  StepState,
} from "./types";

/** A step's state on the map: the server's, or open where it gives none. */
export type StationState = StepState | "open";

export interface Station {
  kind: "station";
  step: FlowStep;
  phase: FlowPhase;
  state: StationState;
  reason: StepReason | null;
  /** The step the harness suggests next; never a gate. */
  suggested: boolean;
  /** In a phase before the one the project's entry point joins at. */
  beforeEntry: boolean;
  /** Something here waits on the researcher: a document to decide on, or a question. */
  waiting: boolean;
}

export interface DecisionPoint {
  kind: "decision";
  decision: Decision;
  /** Asked from the entry point and not answered yet. */
  waiting: boolean;
}

export type LineItem = Station | DecisionPoint;

export interface Line {
  phase: FlowPhase;
  items: LineItem[];
  /** The entry points that join at this phase. */
  entries: FlowEntry[];
  /** The steps that count towards the phase: those in scope. */
  counted: number;
  /** Of those, how many are done or skipped. */
  finished: number;
}

/** What waits on the researcher: documents whose latest version awaits their decision. */
export interface Waiting {
  documentIds: ReadonlySet<string>;
  documentKinds: ReadonlySet<string>;
}

export const NOTHING_WAITING: Waiting = { documentIds: new Set(), documentKinds: new Set() };

/** The documents whose latest version is proposed, awaiting the researcher's decision. */
export function waitingDocuments(documents: readonly ProjectDocument[]): Waiting {
  const awaiting = documents.filter((d) => d.versions.at(-1)?.state === "proposed");
  return {
    documentIds: new Set(awaiting.map((d) => d.document_id)),
    documentKinds: new Set(awaiting.map((d) => d.document_kind)),
  };
}

function isWaiting(reason: StepReason | null, waiting: Waiting): boolean {
  if (!reason || reason.source !== "produced" || reason.state === "done") return false;
  return (
    (reason.document_id !== undefined && waiting.documentIds.has(reason.document_id)) ||
    (reason.document_kind !== undefined && waiting.documentKinds.has(reason.document_kind))
  );
}

function finishedState(state: StationState): boolean {
  return state === "done" || state === "skipped";
}

/** The map's lines, one per phase, in the flow's order. */
export function journey(
  flow: ProcessFlow,
  progress: ProjectProgress | null,
  waiting: Waiting = NOTHING_WAITING,
): Line[] {
  const startsAt = flow.entries.find((e) => e.number === progress?.entry)?.starts_at ?? null;
  const before = new Map<string, Decision[]>();
  for (const decision of progress?.decisions ?? []) {
    before.set(decision.before, [...(before.get(decision.before) ?? []), decision]);
  }
  return flow.phases.map((phase) => {
    const items: LineItem[] = [];
    let counted = 0;
    let finished = 0;
    for (const step of phase.steps) {
      for (const decision of before.get(step.id) ?? []) {
        items.push({
          kind: "decision",
          decision,
          waiting: decision.asked && decision.answer_values === null,
        });
      }
      const state: StationState = progress?.steps[step.id] ?? "open";
      const reason = progress?.reasons?.[step.id] ?? null;
      if (!step.out_of_scope) {
        counted += 1;
        if (finishedState(state)) finished += 1;
      }
      items.push({
        kind: "station",
        step,
        phase,
        state,
        reason,
        suggested: progress?.suggested === step.id,
        beforeEntry: startsAt !== null && phase.number < startsAt,
        waiting: isWaiting(reason, waiting),
      });
    }
    return {
      phase,
      items,
      entries: flow.entries.filter((e) => e.starts_at === phase.number),
      counted,
      finished,
    };
  });
}

/** Every station of the map, in order. */
export function stations(lines: readonly Line[]): Station[] {
  return lines.flatMap((l) => l.items.filter((i): i is Station => i.kind === "station"));
}

/** How many things wait on the researcher: stations and decision points. */
export function waitingCount(lines: readonly Line[]): number {
  return lines.reduce((n, l) => n + l.items.filter((i) => i.waiting).length, 0);
}

/** The phase and step for a step id, or null if the flow has none. */
export function locate(
  flow: ProcessFlow,
  stepId: string | null,
): { phase: FlowPhase; step: FlowStep } | null {
  if (!stepId) return null;
  for (const phase of flow.phases) {
    const step = phase.steps.find((s) => s.id === stepId);
    if (step) return { phase, step };
  }
  return null;
}

const KIND_NAME: Record<string, string> = {
  readme: "README",
  data_dictionary: "data dictionary",
  metadata_record: "metadata record",
};

/** A document kind in a researcher's words. */
export function kindName(kind: string): string {
  return KIND_NAME[kind] ?? kind.replaceAll("_", " ");
}

/**
 * Why a step is in its state, in a researcher's words, from the reason the harness gave. The
 * decision the reason names, if any, gives the question and the answer.
 */
export function reasonText(reason: StepReason, decisions: readonly Decision[] = []): string {
  if (reason.source === "marked") {
    return reason.state === "skipped" ? "You chose to skip this." : "You marked this done.";
  }
  if (reason.source === "intake") {
    const decision = decisions.find((d) => d.question_id === reason.question_id);
    if (!decision) return "Skipped because of your answer to a setup question.";
    const answer = decision.answer_labels?.join(", ");
    return answer
      ? `Skipped because you answered “${answer}” to “${decision.prompt}”`
      : `Skipped because of your answer to “${decision.prompt}”`;
  }
  const kind = reason.document_kind ? kindName(reason.document_kind) : "document";
  switch (reason.event) {
    case "inventory_added":
      return "Your files were described in the project's inventory.";
    case "repository_chosen":
      return "A repository was chosen for the project.";
    case "package_built":
      return "The deposit package was built.";
    case "project_validated":
      return reason.state === "done"
        ? "The project passed validation against the repository's requirements."
        : "The last validation found things to fix.";
    case "document_version_added":
      return `A draft ${kind} was proposed and awaits a decision.`;
    case "document_version_decided":
      return `The ${kind} was approved.`;
    default:
      return "The project's record shows this step's work.";
  }
}
