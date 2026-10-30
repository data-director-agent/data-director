import several from "../../fixtures/agents-several.json";
import flowFixture from "../../fixtures/process-flow.json";
import { normalise } from "../manifest/normalise";
import type { RawAgentsResponse } from "../manifest/types";
import { servingIndex, servingStep } from "./serving";
import type { ProcessFlow } from "./types";

const FLOW = flowFixture as ProcessFlow;
const directory = normalise(several as unknown as RawAgentsResponse);

describe("servingStep", () => {
  it("joins a step to the agents whose manifest serves its id", () => {
    const index = servingIndex(directory.agents);
    const vocabularies = FLOW.phases[0]?.steps[1];
    if (!vocabularies) throw new Error("no second step in Phase 1");
    expect(vocabularies.id).toBe("setup.vocabularies");
    expect(servingStep(vocabularies, index)).toEqual(
      directory.agents
        .filter((a) => a.serves.includes("setup.vocabularies"))
        .map((a) => a.id),
    );
    expect(servingStep(vocabularies, index)).toContain("advisor.standards");
  });

  it("finds no agent for a step that no agent serves", () => {
    const step = {
      id: "deposit.upload",
      text: "Upload the files",
      requirements: [],
      optional: false,
    };
    expect(servingStep(step, servingIndex(directory.agents))).toEqual([]);
  });

  it("does not join an agent to a step by a requirement the step names", () => {
    const [first] = directory.agents;
    if (!first) throw new Error("no agent in the fixture");
    const index = servingIndex([{ ...first, serves: ["setup.vocabularies"] }]);
    const formats = {
      id: "preparation.formats",
      text: "Recommend open formats",
      requirements: ["R3"],
      optional: false,
    };
    expect(servingStep(formats, index)).toEqual([]);
  });

  it("joins a step that names no requirement to an agent serving its id", () => {
    const [first] = directory.agents;
    if (!first) throw new Error("no agent in the fixture");
    const index = servingIndex([{ ...first, serves: ["governance.policies"] }]);
    const policies = FLOW.phases[1]?.steps[0];
    if (!policies) throw new Error("no first step in Phase 2");
    expect(policies.requirements).toEqual([]);
    expect(servingStep(policies, index)).toEqual([first.id]);
  });
});
