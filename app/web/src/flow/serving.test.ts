import several from "../../fixtures/agents-several.json";
import flowFixture from "../../fixtures/process-flow.json";
import { normalise } from "../manifest/normalise";
import type { RawAgentsResponse } from "../manifest/types";
import { servingIndex, servingStep } from "./serving";
import type { ProcessFlow } from "./types";

const FLOW = flowFixture as ProcessFlow;
const directory = normalise(several as unknown as RawAgentsResponse);

describe("servingStep", () => {
  it("joins a step's requirements to the agents whose manifest serves them", () => {
    const index = servingIndex(directory.agents);
    const vocabularies = FLOW.phases[0]?.steps[1];
    if (!vocabularies) throw new Error("no second step in Phase 1");
    expect(vocabularies.requirements).toEqual(["R3"]);
    expect(servingStep(vocabularies, index)).toEqual(
      directory.agents.filter((a) => a.serves.includes("R3")).map((a) => a.id),
    );
    expect(servingStep(vocabularies, index)).toContain("standards.advisor");
  });

  it("finds no agent for a step that names no requirement", () => {
    const step = { text: "Upload the files", requirements: [], optional: false };
    expect(servingStep(step, servingIndex(directory.agents))).toEqual([]);
  });

  it("names an agent once when it serves two of a step's requirements", () => {
    const [first] = directory.agents;
    if (!first) throw new Error("no agent in the fixture");
    const index = servingIndex([{ ...first, serves: ["R2", "R6"] }]);
    const step = { text: "Complete fields", requirements: ["R2", "R6"], optional: false };
    expect(servingStep(step, index)).toEqual([first.id]);
  });
});
