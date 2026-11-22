import { render } from "@testing-library/react";

import fixture from "../../../fixtures/projects.json";
import {
  type ActiveProject,
  ActiveProjectTestContext,
} from "../../project/active";
import {
  type ProjectApi,
  type ProjectSummary,
  ProjectApiContext,
} from "../../project/api";
import { ProjectLanding } from "./ProjectLanding";

const PROJECTS = fixture as ProjectSummary[];
const FIRST = PROJECTS[0] as ProjectSummary;

function renderLanding(
  projects: () => Promise<ProjectSummary[]>,
  projectId: string | null = null,
) {
  const api = { projects } as unknown as ProjectApi;
  const value: ActiveProject = {
    projectId,
    projects: [],
    setProjectId: vi.fn(),
    reloadProjects: vi.fn(),
  };
  return render(
    <ActiveProjectTestContext.Provider value={value}>
      <ProjectApiContext.Provider value={api}>
        <ProjectLanding />
      </ProjectApiContext.Provider>
    </ActiveProjectTestContext.Provider>,
  );
}

describe("ProjectLanding", () => {
  beforeEach(() => history.pushState(null, "", "/project"));

  it("opens the current project's page in its place", async () => {
    renderLanding(() => Promise.resolve(PROJECTS), FIRST.project_id);
    await vi.waitFor(() =>
      expect(location.pathname).toBe(`/projects/${FIRST.project_id}`),
    );
  });

  it("opens the list of projects when none is current", async () => {
    renderLanding(() => Promise.resolve(PROJECTS));
    await vi.waitFor(() => expect(location.pathname).toBe("/projects"));
  });

  it("does not open a remembered project the server no longer lists", async () => {
    renderLanding(() => Promise.resolve(PROJECTS), "gone");
    await vi.waitFor(() => expect(location.pathname).toBe("/projects"));
  });

  it("opens the list of projects when the projects cannot be read", async () => {
    renderLanding(() => Promise.reject(new Error("down")), FIRST.project_id);
    await vi.waitFor(() => expect(location.pathname).toBe("/projects"));
  });
});
