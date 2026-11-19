// The agent card is written by sdk/tests/test_agent_view_fixtures.py from what the SDK serves.
import { AGENT_SPEC_URI, type AgentCard, type AgentSpec, agentSpecOf, MANIFEST_URI, readCard } from "../src";
import agentCard from "./fixtures/agent-card.json";

/**
 * A harness's card, as harness/src/dd_harness/transport/a2a.py builds it: one skill per agent and
 * the `manifest/v0` extension listing each agent's specification. Made from the agent card, so
 * that the SDK's test suite need not import the harness.
 */
function harnessCard(): unknown {
  const params = agentCard.capabilities.extensions.find((x) => x.uri === AGENT_SPEC_URI)?.params;
  return {
    name: "Data Director Harness",
    version: "0.1.0",
    capabilities: {
      streaming: false,
      extensions: [{ uri: MANIFEST_URI, description: "The agents this harness may invoke.", params: { agents: [params] } }],
    },
    supportedInterfaces: agentCard.supportedInterfaces,
    skills: agentCard.skills,
  };
}

/** A fresh copy of a card fixture, as it arrives over the wire. */
export function fixture(name: "agent-card.json" | "harness-card.json"): unknown {
  return name === "agent-card.json" ? structuredClone(agentCard) : harnessCard();
}

/** A card fixture, read; fails the test if it does not read. */
export function card(name: "agent-card.json" | "harness-card.json"): AgentCard {
  const read = readCard(fixture(name)).card;
  if (!read) throw new Error(`${name} is not a card`);
  return read;
}

/** The agent card fixture's specification. */
export function spec(): AgentSpec {
  const read = agentSpecOf(card("agent-card.json"));
  if (!read) throw new Error("agent-card.json has no specification");
  return read;
}
