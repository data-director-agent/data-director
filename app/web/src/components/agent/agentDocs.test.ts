import { agentDocsUrl } from "./agentDocs";

describe("agentDocsUrl", () => {
  it("names the page under agents/ with the id's dot as a hyphen", () => {
    expect(agentDocsUrl("advisor.dmp")).toBe(
      "https://data-director-agent.github.io/data-director/agents/advisor-dmp/",
    );
  });
});
