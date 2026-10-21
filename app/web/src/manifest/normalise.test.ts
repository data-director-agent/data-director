import reference from "../../fixtures/agents.json";
import several from "../../fixtures/agents-several.json";
import { gateStatus, normalise } from "./normalise";
import type { RawAgentsResponse, RawManifestEntry } from "./types";

const referenceSet = reference as unknown as RawAgentsResponse;
const severalAgents = several as unknown as RawAgentsResponse;

function entry(overrides: Partial<RawManifestEntry>): RawManifestEntry {
  const r3 = referenceSet.agents[0];
  if (!r3) throw new Error("the reference fixture lists no agent");
  return { ...r3, ...overrides };
}

describe("normalise", () => {
  it("draws the reference set: R3, permitted, as the profile assigns it", () => {
    const directory = normalise(referenceSet);
    expect(directory.agents.map((a) => a.id)).toEqual(["r3.standards-advisor"]);
    expect(directory.agents[0]?.gate).toEqual({ kind: "permitted", actionClass: "advise" });
    expect(directory.profileRef).toBe("profile:data-director-app@v1");
    expect(directory.actingFor.assurance).toBe("asserted");
  });

  it("keeps every agent of different shapes and names none specially", () => {
    const directory = normalise(severalAgents);
    expect(directory.agents.map((a) => [a.id, a.groundingMode, a.payload])).toEqual([
      ["fact.checker", "retrieval", "FactCheck"],
      ["hello.world", "none", "Greeting"],
      ["quality.reviewer", "input_only", "QualityReview"],
      ["r3.standards-advisor", "retrieval", "Recommendations"],
      ["stub.abstain", "none", null],
    ]);
  });

  it("marks every oversight field undeclared, never defaulted", () => {
    for (const agent of normalise(severalAgents).agents) {
      expect(Object.values(agent.oversight).every((v) => v.state === "undeclared")).toBe(true);
    }
  });

  it("lists derivations by field path", () => {
    const r3 = normalise(referenceSet).agents[0];
    expect(r3?.derivations).toEqual([
      { path: "items.kind", how: "lexical" },
      { path: "items.rationale", how: "model" },
    ]);
  });

  it("lists agents that could not be registered, with the reason", () => {
    const directory = normalise({
      ...referenceSet,
      unavailable: { "http://127.0.0.1:8101": "connection refused" },
      incompatible: { old: "contract 0.7.0, harness 0.8.0" },
    });
    expect(directory.unregistered).toEqual([
      { name: "http://127.0.0.1:8101", state: "unavailable", reason: "connection refused" },
      { name: "old", state: "incompatible", reason: "contract 0.7.0, harness 0.8.0" },
    ]);
  });
});

describe("gateStatus", () => {
  it("is not-permitted when the profile does not list the agent", () => {
    const r3 = severalAgents.agents.find((a) => a.agent_id === "r3.standards-advisor");
    expect(r3 && gateStatus(r3)).toEqual({ kind: "not-permitted" });
  });

  it("is a mismatch when the card declares another class than the profile assigns", () => {
    expect(gateStatus(entry({ action_class: "advise", assigned_action_class: "deposit" }))).toEqual(
      { kind: "mismatch", declared: "advise", assigned: "deposit" },
    );
  });

  it("needs approval when the assigned class requires it", () => {
    expect(
      gateStatus(
        entry({
          action_class: "metadata_write",
          assigned_action_class: "metadata_write",
          requires_approval: true,
        }),
      ),
    ).toEqual({ kind: "needs-approval", actionClass: "metadata_write" });
  });
});
