import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import flowFixture from "../../../fixtures/process-flow.json";
import { FlowApiContext } from "../../flow/api";
import type { ProcessFlow } from "../../flow/types";
import { type StewardApi, type StewardProject, StewardApiContext } from "../../project/steward";
import { PROJECTS, fakeStewardApi } from "../../test/steward";
import { StewardProjectsPage, phaseOf } from "./StewardProjectsPage";

const FLOW = flowFixture as ProcessFlow;

function first(): StewardProject {
  const [project] = PROJECTS;
  if (!project) throw new Error("no project in the fixture");
  return project;
}

const PROJECT = first();

function shown(api: StewardApi) {
  return render(
    <FlowApiContext.Provider value={{ get: () => Promise.resolve(FLOW) }}>
      <StewardApiContext.Provider value={api}>
        <StewardProjectsPage />
      </StewardApiContext.Provider>
    </FlowApiContext.Provider>,
  );
}

describe("a data steward's projects", () => {
  it("lists each project with a link that opens it as the steward's view", async () => {
    const api = fakeStewardApi();
    const { container } = shown(api);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(PROJECTS.length);
    const [row] = rows;
    if (!row) throw new Error("no row");
    expect(within(row).getByRole("link", { name: PROJECT.title ?? "" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT.project_id}`,
    );
    expect(within(row).getByText(PROJECT.created_by.name)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
    expect(api.projects).toHaveBeenCalledWith(null, expect.anything());
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows each run's outcome and what waits for review", async () => {
    const referred = "019a0000-0000-7000-8000-000000000002";
    const project: StewardProject = {
      ...PROJECT,
      recent_runs: [
        {
          invocation_id: referred,
          agent_id: "advisor.metadata",
          status: "referred",
          reason_code: "policy_requires_approval",
          completed_at: "2026-01-02T00:00:00+00:00",
          acting_for: "A Researcher",
          project_id: PROJECT.project_id,
        },
      ],
      awaiting_review: { proposed_versions: 2, fact_proposals: 0, referred_runs: [referred] },
    };
    shown(fakeStewardApi(undefined, undefined, [project]));
    const row = within(await screen.findByRole("table")).getAllByRole("row")[1];
    if (!row) throw new Error("no row");
    expect(within(row).getByText("Referred to a person")).toBeInTheDocument();
    expect(within(row).getByText(/step referred to you/)).toBeInTheDocument();
    expect(within(row).getByText(/document versions/)).toBeInTheDocument();
  });

  it("reads the next page when asked", async () => {
    const api = fakeStewardApi();
    const later: StewardProject = { ...PROJECT, project_id: "019a0000-0000-7000-8000-0000000000a0", title: "Older" };
    api.projects
      .mockResolvedValueOnce({ items: PROJECTS, next: PROJECT.project_id })
      .mockResolvedValueOnce({ items: [later], next: null });
    shown(api);
    await userEvent.click(await screen.findByRole("button", { name: "Show more projects" }));
    expect(await screen.findByRole("link", { name: "Older" })).toBeInTheDocument();
    expect(api.projects).toHaveBeenLastCalledWith(PROJECT.project_id);
    expect(screen.queryByRole("button", { name: "Show more projects" })).not.toBeInTheDocument();
  });

  it("says so when there are no projects", async () => {
    shown(fakeStewardApi(undefined, undefined, []));
    expect(await screen.findByText(/No project is waiting for your teams/)).toBeInTheDocument();
  });

  it("says when the projects cannot be read", async () => {
    const api = fakeStewardApi();
    api.projects.mockRejectedValue(new Error("offline"));
    shown(api);
    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  });

  it("names the phase with the suggested step, else the first unfinished one", () => {
    expect(phaseOf(null, PROJECT)).toBeNull();
    const [, later] = FLOW.phases;
    const step = later?.steps[0];
    if (!later || !step) throw new Error("the flow has fewer than two phases");
    const suggested = { ...PROJECT, progress: { ...PROJECT.progress, suggested: step.id } };
    expect(phaseOf(FLOW, suggested)).toBe(later.name);
    expect(phaseOf(FLOW, PROJECT)).toBe(FLOW.phases[0]?.name);
  });
});
