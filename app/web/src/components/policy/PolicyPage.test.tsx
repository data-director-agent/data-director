import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import agentsFixture from "../../../fixtures/agents.json";
import several from "../../../fixtures/agents-several.json";
import policyFixture from "../../../fixtures/policy.json";
import { type Directory, normalise } from "../../manifest/normalise";
import type { RawAgentsResponse, RawManifestEntry } from "../../manifest/types";
import {
  type Policy,
  type PolicyApi,
  PolicyApiContext,
} from "../../policy/api";
import { PolicyPage } from "./PolicyPage";

const POLICY = policyFixture as Policy;
const REFERENCE = agentsFixture as unknown as RawAgentsResponse;
const STRANGER = (several as unknown as RawAgentsResponse).agents.find(
  (agent) => agent.agent_id === "stub.abstain",
) as RawManifestEntry;

function directory(extra: RawManifestEntry[] = []): Directory {
  return normalise({ ...REFERENCE, agents: [...REFERENCE.agents, ...extra] });
}

function rowWith(rows: HTMLElement[], text: string): HTMLElement {
  const row = rows.find((candidate) => within(candidate).queryByText(text));
  if (!row) throw new Error(`no row names ${text}`);
  return row;
}

function renderPage(
  dir: Directory,
  api: PolicyApi = { get: () => Promise.resolve(POLICY) },
) {
  return render(
    <PolicyApiContext.Provider value={api}>
      <PolicyPage directory={dir} />
    </PolicyApiContext.Provider>,
  );
}

describe("PolicyPage", () => {
  it("shows the profile the server holds runs to", async () => {
    renderPage(directory());
    expect(
      screen.getByRole("heading", { level: 1, name: "Policy" }),
    ).toBeVisible();
    expect(await screen.findByText(POLICY.profile.ref)).toBeVisible();
    expect(screen.getByText(POLICY.profile.description)).toBeVisible();
    expect(screen.getByText(POLICY.profile.digest)).toBeVisible();
  });

  it("lists every agent the profile allows, with its action class and what happens here", async () => {
    renderPage(directory());
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(POLICY.agents.length);
    const reached = rowWith(rows, "Standards Librarian");
    expect(within(reached).getByRole("link")).toHaveAttribute(
      "href",
      "/agents?agent=advisor.standards",
    );
    expect(within(reached).getByText("Permitted")).toBeVisible();
    // An agent the profile allows but this deployment does not reach is named by its identifier.
    expect(
      within(rowWith(rows, "example.hello")).getByText("Not reachable"),
    ).toBeVisible();
  });

  it("names the action classes that need a steward's approval", async () => {
    renderPage(directory());
    const section = await screen.findByRole("region", {
      name: /need a data steward's approval/,
    });
    for (const actionClass of POLICY.actions_requiring_approval) {
      expect(within(section).getByText(actionClass)).toBeVisible();
    }
  });

  it("names the agents it reaches but does not allow", async () => {
    renderPage(directory([{ ...STRANGER, assigned_action_class: null }]));
    const section = await screen.findByRole("region", {
      name: /does not allow/,
    });
    expect(
      within(section).getByRole("link", { name: "stub.abstain" }),
    ).toHaveAttribute("href", "/agents?agent=stub.abstain");
  });

  it("says when the profile names no conversation agent and allows nothing", async () => {
    const bare: Policy = {
      ...POLICY,
      profile: { ...POLICY.profile, description: "", orchestrator: null },
      agents: [],
      actions_requiring_approval: [],
    };
    renderPage(directory(), { get: () => Promise.resolve(bare) });
    expect(await screen.findByText(/offers no conversation/)).toBeVisible();
    expect(screen.getByText("Not described")).toBeVisible();
    expect(screen.getByText(/allows no agent to run/)).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says when the policy cannot be read", async () => {
    renderPage(directory(), {
      get: () => Promise.reject(new Error("the server answered 500")),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the server answered 500",
    );
  });

  it("has no accessibility violations", async () => {
    const { container } = renderPage(
      directory([{ ...STRANGER, assigned_action_class: null }]),
    );
    await screen.findByRole("table");
    expect(await axe(container)).toHaveNoViolations();
  });
});
