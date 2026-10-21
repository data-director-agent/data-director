/**
 * The conductor's stages for one run, inferred after it has ended.
 *
 * The stages are the conductor's, the same for every agent: policy gate, input check, the agent,
 * the grounding check and the source check (harness/src/dd_harness/conductor.py), then a human
 * review that is not built yet (#72, #73). Until runs stream over AG-UI (#68, #69) the page
 * cannot watch them happen, so each is read back from the envelope: a problem type names the
 * stage that stopped the run, and the checks' stored summaries say how the checks went.
 */

import type { Checks, RunResult } from "./types";

export type StageState =
  | "waiting"
  | "running"
  | "passed"
  | "failed"
  | "stopped"
  | "finished"
  | "not-reached"
  | "nothing-to-check"
  | "not-built";

export interface Stage {
  id: "gate" | "input" | "agent" | "grounding" | "sources" | "review";
  label: string;
  state: StageState;
  detail?: string;
  /** Issues that will build a stage that is not built yet. */
  issues?: number[];
}

const LABELS: Record<Stage["id"], string> = {
  gate: "Policy gate",
  input: "Input check",
  agent: "Agent",
  grounding: "Grounding check",
  sources: "Source check",
  review: "Human review",
};

const REVIEW: Stage = {
  id: "review",
  label: LABELS.review,
  state: "not-built",
  detail: "Proposed changes will wait here for a person to approve them.",
  issues: [72, 73],
};

const PROBLEM_BASE = "https://w3id.org/data-director/problems/";

/** The problem type's last segment, such as `input-not-accepted`, or null. */
export function problemSlug(type: string | undefined | null): string | null {
  if (!type) return null;
  return type.startsWith(PROBLEM_BASE) ? type.slice(PROBLEM_BASE.length) : type;
}

/** Every stage waiting, then the first one running: what the page shows while it waits. */
export function pendingStages(): Stage[] {
  return (["gate", "input", "agent", "grounding", "sources"] as const)
    .map((id): Stage => ({ id, label: LABELS[id], state: id === "gate" ? "running" : "waiting" }))
    .concat(REVIEW);
}

function stage(id: Stage["id"], state: StageState, detail?: string): Stage {
  return detail === undefined
    ? { id, label: LABELS[id], state }
    : { id, label: LABELS[id], state, detail };
}

function check(id: "grounding" | "sources", checks: Checks, ranOver: boolean): Stage {
  const report = checks[id];
  if (!ranOver) return stage(id, "nothing-to-check", "The run stopped before the agent answered.");
  if (report === null) return stage(id, "not-reached");
  return stage(id, report.passed ? "passed" : "failed", report.summary);
}

export function inferStages({ envelope, checks }: RunResult): Stage[] {
  const slug = problemSlug(envelope.problem?.type);
  const { status, reason_code } = envelope.outcome;
  const refusedByGate = slug === "agent-not-permitted" || slug === "action-class-mismatch";
  const needsApproval = status === "referred" && reason_code === "policy_requires_approval";

  if (refusedByGate || needsApproval) {
    return [
      stage(
        "gate",
        refusedByGate ? "failed" : "stopped",
        refusedByGate ? envelope.problem?.title : "Referred: this agent's runs need approval.",
      ),
      stage("input", "not-reached"),
      stage("agent", "not-reached"),
      check("grounding", checks, false),
      check("sources", checks, false),
      REVIEW,
    ];
  }
  if (slug === "input-not-accepted") {
    return [
      stage("gate", "passed"),
      stage("input", "failed", envelope.problem?.detail ?? undefined),
      stage("agent", "not-reached"),
      check("grounding", checks, false),
      check("sources", checks, false),
      REVIEW,
    ];
  }
  return [
    stage("gate", "passed"),
    stage("input", "passed"),
    slug === "agent-error"
      ? stage("agent", "failed", envelope.problem?.detail ?? undefined)
      : stage(
          "agent",
          "finished",
          slug === "grounding-violation"
            ? "Answered, but the checks below withheld its output."
            : `Answered: ${status}`,
        ),
    check("grounding", checks, slug !== "agent-error"),
    check("sources", checks, slug !== "agent-error"),
    REVIEW,
  ];
}
