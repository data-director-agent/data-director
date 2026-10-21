import reference from "../../fixtures/agents.json";
import abstained from "../../fixtures/run-abstained.json";
import succeeded from "../../fixtures/run-succeeded.json";
import soil from "../../../config/examples/soil-chemistry.profile.json";
import { normalise } from "../manifest/normalise";
import type { RawAgentsResponse } from "../manifest/types";
import { check, planFields, toDocument, toForm } from "./form";
import { inferStages, problemSlug } from "./stages";
import type { RunResult } from "./types";

function defined<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`no ${what} in the fixture`);
  return value;
}

const standards = defined(normalise(reference as unknown as RawAgentsResponse).agents[0], "agent");
const profile = defined(standards.schemas.DatasetProfile, "DatasetProfile schema");

describe("the run form's model", () => {
  const plan = defined(planFields(profile), "plan");

  it("asks for the title and description first, then lists, then records", () => {
    expect(plan.map((f) => [f.name, f.shape.kind])).toEqual([
      ["title", "scalar"],
      ["description", "scalar"],
      ["keywords", "list"],
      ["media_types", "list"],
      ["themes", "list"],
      ["fields", "records"],
    ]);
  });

  it("gives back the document it was given", () => {
    expect(toDocument(plan, toForm(plan, soil), "DatasetProfile")).toEqual(soil);
  });

  it("leaves empty fields out rather than sending empty text", () => {
    expect(toDocument(plan, toForm(plan, {}), "DatasetProfile")).toEqual({
      schema_class: "DatasetProfile",
    });
  });

  it("requires a record's required fields", () => {
    const state = toForm(plan, { fields: [{ field_type: "string" }] });
    expect(check(plan, state, "p")).toEqual([
      { target: "p-fields-0-name", message: "Enter name of field 1" },
    ]);
  });

  it("gives up on a shape it cannot draw", () => {
    expect(
      planFields({ properties: { nested: { type: "object", properties: { a: { type: "string" } } } } }),
    ).toBeNull();
  });
});

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
