/**
 * Which agents serve a step of the process flow: those whose manifest entry `serves` any of the
 * step's requirements (ADR-0028). The same join as `plan` in `dd_sdk.process_flow`, so the shell
 * keeps no map of agents to phases.
 */

import type { AgentView } from "../manifest/normalise";
import type { FlowStep } from "./types";

/** Requirement ID → the IDs of the agents serving it, each list sorted. */
export function servingIndex(agents: AgentView[]): Map<string, string[]> {
  const index = new Map<string, string[]>();
  for (const agent of [...agents].sort((a, b) => a.id.localeCompare(b.id))) {
    for (const requirement of agent.serves) {
      index.set(requirement, [...(index.get(requirement) ?? []), agent.id]);
    }
  }
  return index;
}

/** The agents serving any of the step's requirements, in order and without repeats. */
export function servingStep(step: FlowStep, index: Map<string, string[]>): string[] {
  return [...new Set(step.requirements.flatMap((r) => index.get(r) ?? []))];
}
