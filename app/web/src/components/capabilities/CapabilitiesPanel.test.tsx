import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { App } from "../../App";
import reference from "../../../fixtures/agents.json";
import several from "../../../fixtures/agents-several.json";
import { type Directory, normalise, normaliseAgent } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import { DEVELOPMENT, WithSession, fakeSessionApi } from "../../test/session";
import { AgentDirectory } from "./AgentDirectory";
import { CapabilitiesPanel } from "./CapabilitiesPanel";

const severalAgents = several as unknown as RawAgentsResponse;
const directory = normalise(severalAgents);

function agent(id: string) {
  const found = directory.agents.find((a) => a.id === id);
  if (!found) throw new Error(`no ${id} in the fixture`);
  return found;
}

describe("CapabilitiesPanel", () => {
  it.each(directory.agents.map((a) => a.id))("%s has no axe violations", async (id) => {
    const { container } = render(<CapabilitiesPanel agent={agent(id)} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("names the agent in a heading and shows what it takes and returns", () => {
    render(<CapabilitiesPanel agent={agent("quality.reviewer")} />);
    expect(screen.getByRole("heading", { level: 2, name: "quality.reviewer" })).toBeVisible();
    expect(screen.getByText("metadata record")).toBeVisible();
    expect(screen.getByText("quality review")).toBeVisible();
  });

  it("says when an agent returns no result", () => {
    render(<CapabilitiesPanel agent={agent("stub.abstain")} />);
    expect(screen.getByText("No result: it only reports an outcome")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "How each field is produced" })).toBeNull();
  });

  it("tables each declared derivation", () => {
    render(<CapabilitiesPanel agent={agent("standards.advisor")} />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: /items\.rationale Written by a language model/ }))
      .toBeVisible();
  });

  it("says when an agent has no AI model and is deterministic", () => {
    render(<CapabilitiesPanel agent={agent("standards.advisor")} />);
    expect(screen.getByText(/This agent is deterministic software/)).toBeVisible();
  });

  it("does not call an agent deterministic when its card says nothing about models", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "standards.advisor");
    if (!raw) throw new Error("no standards.advisor in the fixture");
    const card = { ...raw };
    delete card.models;
    render(<CapabilitiesPanel agent={normaliseAgent(card)} />);
    expect(screen.getByText(/does not say whether it uses an AI model/)).toBeVisible();
    expect(screen.queryByText(/deterministic/)).toBeNull();
  });

  it("names the provider and model an agent sends data to", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "standards.advisor");
    if (!raw) throw new Error("no standards.advisor in the fixture");
    const view = normaliseAgent({
      ...raw,
      models: [{ provider: "anthropic", model: "claude-test", hosting: "hosted" }],
    });
    render(<CapabilitiesPanel agent={view} />);
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("Language model, remote: Anthropic claude-test");
    expect(item).toHaveTextContent("outside this institution");
  });

  it("says a locally hosted model is local", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "standards.advisor");
    if (!raw) throw new Error("no standards.advisor in the fixture");
    const view = normaliseAgent({
      ...raw,
      models: [{ provider: "ollama", model: "llama-test", hosting: "local" }],
    });
    render(<CapabilitiesPanel agent={view} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("Language model, local: ollama llama-test");
  });

  it("says the grounding check is not proof of retrieval", () => {
    render(<CapabilitiesPanel agent={agent("standards.advisor")} />);
    expect(screen.getByText(/does not prove the agent retrieved them/)).toBeVisible();
  });

  it("shows each undeclared oversight field as Not declared, and reliability as unsubstantiated", () => {
    render(<CapabilitiesPanel agent={agent("hello.world")} />);
    expect(screen.getAllByText("Not declared")).toHaveLength(5);
    expect(screen.getByText(/Treat its reliability as unsubstantiated/)).toBeVisible();
  });

  it("says when the profile does not permit the agent", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "standards.advisor");
    if (!raw) throw new Error("no standards.advisor");
    render(<CapabilitiesPanel agent={normaliseAgent({ ...raw, assigned_action_class: null })} />);
    expect(screen.getByText("Not permitted")).toBeVisible();
  });

  it("says when the declared and assigned action classes differ", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "hello.world");
    if (!raw) throw new Error("no hello.world");
    render(
      <CapabilitiesPanel agent={normaliseAgent({ ...raw, assigned_action_class: "deposit" })} />,
    );
    expect(screen.getByText("Refused")).toBeVisible();
    expect(screen.getByText("deposit")).toBeVisible();
  });
});

describe("AgentDirectory", () => {
  it("selects an agent from the keyboard and shows its panel", async () => {
    const user = userEvent.setup();
    render(<AgentDirectory directory={directory} />);
    expect(screen.getByRole("heading", { level: 2, name: "hello.world" })).toBeVisible();

    await user.tab();
    expect(screen.getByRole("option", { name: /^hello\.world/ })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /^quality\.reviewer/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { level: 2, name: "quality.reviewer" })).toBeVisible();
  });

  it("lists agents that could not be registered", async () => {
    const withMissing: Directory = {
      ...directory,
      unregistered: [{ name: "http://127.0.0.1:8101", state: "unavailable", reason: "refused" }],
    };
    const { container } = render(<AgentDirectory directory={withMissing} />);
    expect(screen.getByRole("heading", { name: "Agents that could not be registered" }))
      .toBeVisible();
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when no agent is registered", () => {
    render(<AgentDirectory directory={{ ...directory, agents: [] }} />);
    expect(screen.getByText("No agents are registered with this deployment.")).toBeVisible();
  });
});

describe("App", () => {
  it("loads the directory and names whom runs act for", async () => {
    history.pushState(null, "", "/");
    const { container } = render(
      <WithSession api={fakeSessionApi(DEVELOPMENT)}>
        <App load={() => Promise.resolve(normalise(reference as unknown as RawAgentsResponse))} />
      </WithSession>,
    );
    // The reference set has no orchestrator, so the home page points to the directory.
    await userEvent.click(await screen.findByRole("link", { name: "Open the agent directory" }));
    expect(await screen.findByRole("heading", { name: "standards.advisor" })).toBeVisible();
    expect(screen.getByText(/asserted by the operator, not authenticated/)).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("reports a failure to load as an alert", async () => {
    render(
      <WithSession api={fakeSessionApi(DEVELOPMENT)}>
        <App load={() => Promise.reject(new Error("the server answered 500"))} />
      </WithSession>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("the server answered 500");
  });
});
