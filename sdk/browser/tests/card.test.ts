
import { card as cardOf, fixture, spec as helloSpec } from "./fixtures";
import {
  AGENT_SPEC_URI,
  agentSpecOf,
  findExtension,
  MANIFEST_URI,
  manifestOf,
  readAgentSpec,
  readCard,
} from "../src";


describe("readCard", () => {
  it("reads an agent's card as served, with nothing to report", () => {
    const { card, issues } = readCard(fixture("agent-card.json"));
    expect(issues).toEqual([]);
    expect(card?.name).toBe("test.spec");
    expect(card?.supportedInterfaces?.[0]?.protocolBinding).toBe("JSONRPC");
    expect(card?.skills?.[0]?.tags).toContain("data-director");
    expect(card && findExtension(card, AGENT_SPEC_URI)?.required).toBe(true);
  });

  it.each([
    [null, "The card is not a JSON object."],
    [[], "The card is not a JSON object."],
    [{ description: "no name" }, "The card has no name, so it is not an A2A agent card."],
  ])("refuses %j", (value, issue) => {
    expect(readCard(value)).toEqual({ card: null, issues: [issue] });
  });

  it("drops what it cannot read, says so, and keeps fields it does not know", () => {
    const { card, issues } = readCard({
      name: "odd",
      version: 3,
      provider: "me",
      capabilities: { streaming: true, extensions: [{ uri: "urn:x", params: { a: 1 } }, { nope: 1 }] },
      skills: [{ id: "s", tags: ["a", 2] }, "skill"],
      supportedInterfaces: "http://x",
      securitySchemes: [],
      defaultInputModes: ["text/plain"],
      futureField: { kept: true },
    });
    expect(card).toEqual({
      name: "odd",
      capabilities: { streaming: true, extensions: [{ uri: "urn:x", params: { a: 1 } }] },
      skills: [{ id: "s", tags: ["a"] }],
      defaultInputModes: ["text/plain"],
      futureField: { kept: true },
    });
    expect(issues).toEqual([
      "version is not text.",
      "provider is not an object.",
      "Interface is not a list.",
      "Skill 2 is not readable.",
      "Extension 2 is not readable.",
      "securitySchemes is not an object.",
    ]);
  });

  it("says when capabilities is not an object", () => {
    expect(readCard({ name: "x", capabilities: 1 }).issues).toEqual(["capabilities is not an object."]);
  });
});

describe("the Data Director extensions", () => {
  it("reads an agent's specification from its card", () => {
    const spec = helloSpec();
    expect(spec).toMatchObject({
      id: "test.spec",
      accepts: ["Survey"],
      payload: "Findings",
      groundingMode: "retrieval",
      modelsDeclared: true,
      models: [],
      derivations: [
        { path: "items.kind", how: "lexical", recordedIn: "classification_derivation" },
        { path: "items.rationale", how: "model", recordedIn: "rationale_derivation" },
        { path: "searched.snapshot_ref", how: "registry" },
      ],
    });
    expect(Object.keys(spec.schemas).sort()).toEqual(["Findings", "Survey"]);
    expect(spec.digests.Findings).toMatch(/^[0-9a-f]{64}$/);
  });

  it("reads each agent a harness may invoke from its card", () => {
    const card = cardOf("harness-card.json");
    expect(agentSpecOf(card)).toBeNull();
    expect(findExtension(card, MANIFEST_URI)).toBeDefined();
    expect(manifestOf(card)?.map((a) => a.id)).toEqual(card.skills?.map((s) => s.id));
  });

  it("has no manifest on an agent's own card", () => {
    expect(manifestOf(cardOf("agent-card.json"))).toBeNull();
  });

  it("refuses a specification without its identity, and tidies the rest", () => {
    expect(readAgentSpec({ agent_id: "x" })).toBeNull();
    expect(readAgentSpec("x")).toBeNull();
    const spec = readAgentSpec({
      agent_id: "a",
      version: "1",
      description: "d",
      action_class: "advise",
      grounding_mode: "none",
      accepts: ["A", 1],
      payload: 2,
      schemas: { A: { digest: "d", json_schema: { type: "object" } }, B: { digest: "d" } },
      derivations: { x: { how: "model" }, y: "model" },
      serves: ["s", null],
      models: [{ provider: "p", model: "m", hosting: "local" }, "m"],
      title: "Ada",
    });
    expect(spec).toMatchObject({
      accepts: ["A"],
      payload: null,
      contractVersion: "",
      schemas: { A: { type: "object" } },
      derivations: [{ path: "x", how: "model" }],
      serves: ["s"],
      models: [{ provider: "p", model: "m", hosting: "local" }],
      title: "Ada",
    });
    expect(readAgentSpec({ ...{ agent_id: "a", version: "1", description: "d", action_class: "a", grounding_mode: "none" } })?.modelsDeclared).toBe(false);
  });
});
