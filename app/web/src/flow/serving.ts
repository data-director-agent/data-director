/**
 * Which agents serve a step of the process flow: those whose manifest entry `serves` the step's id
 * or any of its requirements (ADR-0028, ADR-0032). The same join as `plan` in `dd_sdk.process_flow`, so the shell
 * keeps no map of agents to phases.
 */

import type { AgentView } from "../manifest/normalise";
import type { FlowStep } from "./types";

/** Requirement or step ID → the IDs of the agents serving it, each list sorted. */
export function servingIndex(agents: AgentView[]): Map<string, string[]> {
  const index = new Map<string, string[]>();
  for (const agent of [...agents].sort((a, b) => a.id.localeCompare(b.id))) {
    for (const served of agent.serves) {
      index.set(served, [...(index.get(served) ?? []), agent.id]);
    }
  }
  return index;
}

/** The agents serving the step or any of its requirements, in order and without repeats. */
export function servingStep(step: FlowStep, index: Map<string, string[]>): string[] {
  return [...new Set([step.id, ...step.requirements].flatMap((r) => index.get(r) ?? []))];
}
