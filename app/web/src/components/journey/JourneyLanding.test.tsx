import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/projects.json";
import { type ActiveProject, ActiveProjectTestContext } from "../../project/active";
import { type ProjectApi, type ProjectSummary, ProjectApiContext } from "../../project/api";
import { projectName } from "../../project/name";
import { JourneyLanding } from "./JourneyLanding";

const PROJECTS = fixture as ProjectSummary[];
const FIRST = PROJECTS[0] as ProjectSummary;

function renderLanding(listed: ProjectSummary[], projectId: string | null = null) {
  const api = { projects: () => Promise.resolve(listed) } as unknown as ProjectApi;
  const value: ActiveProject = {
    projectId,
    projects: listed,
    setProjectId: vi.fn(),
    reloadProjects: vi.fn(),
  };
  return render(
    <ActiveProjectTestContext.Provider value={value}>
      <ProjectApiContext.Provider value={api}>
        <JourneyLanding />
      </ProjectApiContext.Provider>
    </ActiveProjectTestContext.Provider>,
  );
}

describe("JourneyLanding", () => {
  beforeEach(() => history.pushState(null, "", "/journey"));

  it("opens the current project's journey map in its place", async () => {
    renderLanding(PROJECTS, FIRST.project_id);
    await vi.waitFor(() =>
      expect(location.pathname).toBe(`/projects/${FIRST.project_id}/journey`),
    );
  });

  it("lists the projects to choose from when none is current", async () => {
    const { container } = renderLanding(PROJECTS);
    const link = await screen.findByRole("link", { name: projectName(FIRST) });
    expect(link).toHaveAttribute("href", `/projects/${FIRST.project_id}/journey`);
    expect(location.pathname).toBe("/journey");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("does not open a remembered project the server no longer lists", async () => {
    renderLanding(PROJECTS, "gone");
    expect(await screen.findByRole("link", { name: projectName(FIRST) })).toBeInTheDocument();
    expect(location.pathname).toBe("/journey");
  });

  it("offers to start a project when there is none", async () => {
    renderLanding([]);
    expect(await screen.findByRole("link", { name: "Start a new project" })).toHaveAttribute(
      "href",
      "/projects",
    );
  });
});
