import { problemSlug } from "./problem";

describe("problemSlug", () => {
  it("reads a problem type's slug", () => {
    expect(problemSlug("https://w3id.org/data-director/problems/agent-error")).toBe("agent-error");
    expect(problemSlug("urn:other")).toBe("urn:other");
    expect(problemSlug(null)).toBeNull();
  });
});
