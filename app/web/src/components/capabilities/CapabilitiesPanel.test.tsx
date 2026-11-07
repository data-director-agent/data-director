import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { App } from "../../App";
import reference from "../../../fixtures/agents.json";
import several from "../../../fixtures/agents-several.json";
import { type Directory, normalise, normaliseAgent } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import { DEVELOPMENT, WithSession, fakeSessionApi } from "../../test/session";
import { AgentDetail } from "../agent/AgentDetail";
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
    render(<AgentDetail agent={agent("advisor.quality")} />);
    expect(screen.getByRole("heading", { level: 2, name: "Metadata Reviewer" })).toBeVisible();
    expect(screen.getByText("metadata record")).toBeVisible();
    expect(screen.getByText("quality review")).toBeVisible();
  });

  it("offers nothing to run and no technical tabs", () => {
    render(<AgentDetail agent={agent("advisor.quality")} />);
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/contract/i)).toBeNull();
    expect(screen.queryByRole("heading", { name: /grounds its results/ })).toBeNull();
  });

  it("says when an agent returns no result", () => {
    render(<CapabilitiesPanel agent={agent("stub.abstain")} />);
    expect(screen.getByText("No result: it only reports an outcome")).toBeVisible();
  });

  it("says when an agent has no AI model and is deterministic", () => {
    render(<CapabilitiesPanel agent={agent("advisor.standards")} />);
    expect(screen.getByText(/This agent is deterministic software/)).toBeVisible();
  });

  it("does not call an agent deterministic when its card says nothing about models", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "advisor.standards");
    if (!raw) throw new Error("no advisor.standards in the fixture");
    const card = { ...raw };
    delete card.models;
    render(<CapabilitiesPanel agent={normaliseAgent(card)} />);
    expect(screen.getByText(/does not say whether it uses an AI model/)).toBeVisible();
    expect(screen.queryByText(/deterministic/)).toBeNull();
  });

  it("names the provider and model an agent sends data to", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "advisor.standards");
    if (!raw) throw new Error("no advisor.standards in the fixture");
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
    const raw = severalAgents.agents.find((a) => a.agent_id === "advisor.standards");
    if (!raw) throw new Error("no advisor.standards in the fixture");
    const view = normaliseAgent({
      ...raw,
      models: [{ provider: "ollama", model: "llama-test", hosting: "local" }],
    });
    render(<CapabilitiesPanel agent={view} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("Language model, local: ollama llama-test");
  });

  it("says when the profile does not permit the agent", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "advisor.standards");
    if (!raw) throw new Error("no advisor.standards");
    render(<CapabilitiesPanel agent={normaliseAgent({ ...raw, assigned_action_class: null })} />);
    expect(screen.getByText("Not permitted")).toBeVisible();
  });

  it("says when the declared and assigned action classes differ", () => {
    const raw = severalAgents.agents.find((a) => a.agent_id === "example.hello");
    if (!raw) throw new Error("no example.hello");
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
    expect(screen.getByRole("heading", { level: 2, name: "Metadata Reviewer" })).toBeVisible();

    await user.tab();
    expect(screen.getByRole("option", { name: /^Metadata Reviewer/ })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /^Standards Librarian/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { level: 2, name: "Standards Librarian" })).toBeVisible();
  });

  it("lists agents that could not be registered", async () => {
    const withMissing: Directory = {
      ...directory,
      unregistered: [{ name: "http://127.0.0.1:8101", state: "unavailable", reason: "refused" }],
    };
    const { container } = render(<AgentDirectory directory={withMissing} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Agent unavailable");
    expect(alert).toHaveTextContent("http://127.0.0.1:8101");
    expect(alert).toHaveTextContent("refused");
    // The alert comes before the agents, at the top of the page.
    expect(
      alert.compareDocumentPosition(screen.getByRole("heading", { name: "Agents" })) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when no agent is registered", () => {
    render(<AgentDirectory directory={{ ...directory, agents: [] }} />);
    expect(screen.getByText("No agents are registered with this deployment.")).toBeVisible();
  });
});

describe("App", () => {
  it("loads the directory", async () => {
    history.pushState(null, "", "/");
    const { container } = render(
      <WithSession api={fakeSessionApi(DEVELOPMENT)}>
        <App load={() => Promise.resolve(normalise(reference as unknown as RawAgentsResponse))} />
      </WithSession>,
    );
    // The reference set has no orchestrator, so the home page points to the directory.
    await userEvent.click(await screen.findByRole("link", { name: "Open the agent directory" }));
    expect(await screen.findByRole("heading", { name: "Standards Librarian" })).toBeVisible();
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
