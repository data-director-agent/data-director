import { describe, expect, it } from "vitest";
import flowFixture from "../../fixtures/process-flow.json";

import { startablePrompts } from "./prompts";
import type { ProcessFlow, ProjectProgress } from "./types";

const flow = flowFixture as ProcessFlow;
const steps = flow.phases.flatMap((p) => p.steps);
const offerable = steps.filter((s) => !s.optional && !s.out_of_scope);

function progress(change: Partial<ProjectProgress>): ProjectProgress {
  return { entry: 1, steps: {}, suggested: null, ...change };
}

describe("startablePrompts", () => {
  it("offers nothing when nothing is suggested", () => {
    expect(startablePrompts(flow, progress({}))).toEqual([]);
  });

  it("leads with the suggested step, then open steps after it in order", () => {
    const [first, second, third] = offerable;
    if (!first || !second || !third) throw new Error("the flow fixture is too short");
    const offered = startablePrompts(flow, progress({ suggested: first.id }), 2);
    expect(offered.map((s) => s.id)).toEqual([first.id, second.id]);
    for (const step of offered) expect(step.prompt).toBeTruthy();
  });

  it("leaves out steps done, skipped, optional or out of scope", () => {
    const [first, second, third] = offerable;
    if (!first || !second || !third) throw new Error("the flow fixture is too short");
    const offered = startablePrompts(
      flow,
      progress({
        suggested: first.id,
        steps: { [second.id]: "done", [third.id]: "skipped" },
      }),
      steps.length,
    );
    const ids = offered.map((s) => s.id);
    expect(ids[0]).toBe(first.id);
    expect(ids).not.toContain(second.id);
    expect(ids).not.toContain(third.id);
    for (const step of offered.slice(1)) {
      expect(step.optional || step.out_of_scope).toBe(false);
    }
  });
});
