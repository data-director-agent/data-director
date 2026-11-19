/**
 * The steps to offer as ways to start a conversation, in the order the researcher would take
 * them: the step the harness suggests next, then the open steps after it in the flow. A step is
 * open when the project's progress names no state for it; one done, skipped, optional or out of
 * scope is not offered. The shell decides no state and no suggestion: with nothing suggested,
 * nothing is offered (docs/specs/app.md, "The phases").
 */

import type { FlowStep, ProcessFlow, ProjectProgress } from "./types";

export function startablePrompts(
  flow: ProcessFlow,
  progress: ProjectProgress,
  limit = 3,
): FlowStep[] {
  const steps = flow.phases.flatMap((phase) => phase.steps);
  const from = steps.findIndex((s) => s.id === progress.suggested);
  if (from < 0) return [];
  const [suggested, ...after] = steps.slice(from);
  if (!suggested) return [];
  const open = after.filter(
    (s) => !s.optional && !s.out_of_scope && progress.steps[s.id] === undefined,
  );
  return [suggested, ...open].slice(0, limit);
}
