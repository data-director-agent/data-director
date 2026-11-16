import abstained from "../../fixtures/run-abstained.json";
import succeeded from "../../fixtures/run-succeeded.json";
import { inferStages, problemSlug } from "./stages";
import type { RunResult } from "./types";

describe("the stages read back from a run", () => {
  it("passes every stage of a grounded run, and leaves review not built", () => {
    const stages = inferStages(succeeded as unknown as RunResult);
    expect(stages.map((s) => [s.id, s.state])).toEqual([
      ["gate", "passed"],
      ["input", "passed"],
      ["agent", "finished"],
      ["grounding", "passed"],
      ["sources", "passed"],
      ["review", "not-built"],
    ]);
    expect(stages.at(-1)?.issues).toEqual([72, 73]);
  });

  it("says the agent answered when it abstained", () => {
    const agent = inferStages(abstained as unknown as RunResult)[2];
    expect(agent).toMatchObject({ state: "finished", detail: "Answered: abstained" });
  });

  it("names the input check when the input is not accepted", () => {
    const run = structuredClone(succeeded) as unknown as RunResult;
    run.envelope.outcome = { status: "failed", statement: "no" };
    run.envelope.problem = {
      type: "https://w3id.org/data-director/problems/input-not-accepted",
      title: "Agent does not accept this input",
      detail: "Claim",
    };
    expect(inferStages(run).map((s) => s.state)).toEqual([
      "passed",
      "failed",
      "not-reached",
      "nothing-to-check",
      "nothing-to-check",
      "not-built",
    ]);
  });

  it("stops at the gate when the profile refers the run for approval", () => {
    const run = structuredClone(abstained) as unknown as RunResult;
    run.envelope.outcome = {
      status: "referred",
      reason_code: "policy_requires_approval",
      statement: "needs approval",
    };
    expect(inferStages(run)[0]).toMatchObject({ id: "gate", state: "stopped" });
  });

  it("fails a check whose summary says so", () => {
    const run = structuredClone(succeeded) as unknown as RunResult;
    run.checks.grounding = { passed: false, summary: "grounding: FAILED [retrieval]\n  - G2" };
    expect(inferStages(run)[3]).toMatchObject({ state: "failed" });
  });

  it("reads a problem type's slug", () => {
    expect(problemSlug("https://w3id.org/data-director/problems/agent-error")).toBe("agent-error");
    expect(problemSlug(null)).toBeNull();
  });
});
