import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/projects.json";
import { type ActiveProject, ActiveProjectTestContext } from "../../project/active";
import { type ProjectApi, type ProjectSummary, ProjectApiContext } from "../../project/api";
import { projectName } from "../../project/name";
import { ProjectsPage } from "./ProjectsPage";

// What the server says (app/tests/test_app.py): one untitled project with an inventory of one
// file and one conversation, "My logger data".
const PROJECTS = fixture as ProjectSummary[];
const FIRST = PROJECTS[0] as ProjectSummary;

function renderPage(projects: ProjectApi["projects"], active: Partial<ActiveProject> = {}) {
  const api = { projects, documents: vi.fn(), disclosure: vi.fn(), decide: vi.fn() };
  const value: ActiveProject = {
    projectId: null,
    projects: [],
    setProjectId: vi.fn(),
    reloadProjects: vi.fn(),
    ...active,
  };
  return render(
    <ActiveProjectTestContext.Provider value={value}>
      <ProjectApiContext.Provider value={api as unknown as ProjectApi}>
        <ProjectsPage />
      </ProjectApiContext.Provider>
    </ActiveProjectTestContext.Provider>,
  );
}

describe("ProjectsPage", () => {
  it("lists each project by its first conversation, linked to the project", async () => {
    const { container } = renderPage(() => Promise.resolve(PROJECTS));
    const link = await screen.findByRole("link", { name: "My logger data" });
    expect(link).toHaveAttribute("href", `/projects/${FIRST.project_id}`);
    const card = link.closest("li") as HTMLElement;
    expect(within(card).getByText(/Inventory of 1 file/)).toBeInTheDocument();
    expect(within(card).getByText(/1 conversation\b/)).toBeInTheDocument();
    expect(within(card).getByText("No document drafted yet.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("counts a project's documents by state", async () => {
    const counted = { ...FIRST, documents: { proposed: 2, approved: 1, rejected: 0 } };
    renderPage(() => Promise.resolve([counted]));
    expect(await screen.findByText("2 to review")).toHaveClass("status-warn");
    expect(screen.getByText("1 approved")).toHaveClass("status-ok");
    expect(screen.queryByText(/rejected/)).not.toBeInTheDocument();
  });

  it("says how to start a project when there is none, and starts one with no project active", async () => {
    history.pushState(null, "", "/projects");
    const setProjectId = vi.fn();
    renderPage(() => Promise.resolve([]), { projectId: "p1", setProjectId });
    expect(await screen.findByText(/You have no project yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start a new project" }));
    expect(setProjectId).toHaveBeenCalledWith(null);
    expect(location.pathname).toBe("/");
  });

  it("marks the current project, and opens another's conversations", async () => {
    history.pushState(null, "", "/projects");
    const other = { ...FIRST, project_id: "p2", title: "River loggers" };
    const setProjectId = vi.fn();
    const { container } = renderPage(() => Promise.resolve([FIRST, other]), {
      projectId: FIRST.project_id,
      setProjectId,
    });
    const current = (await screen.findByRole("link", { name: "My logger data" })).closest("li");
    expect(current).toHaveAttribute("aria-current", "true");
    expect(within(current as HTMLElement).getByText("Current project")).toBeVisible();
    const river = screen.getByRole("link", { name: "River loggers" }).closest("li") as HTMLElement;
    expect(river).not.toHaveAttribute("aria-current");
    await userEvent.click(
      within(river).getByRole("button", { name: "Open the conversations of River loggers" }),
    );
    expect(setProjectId).toHaveBeenCalledWith("p2");
    expect(location.pathname).toBe("/");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says why when the projects cannot be read", async () => {
    renderPage(() => Promise.reject(new Error("the server answered 500")));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Data Director could not list your projects: the server answered 500",
    );
  });
});

describe("projectName", () => {
  it("prefers a title the project was given", () => {
    expect(projectName({ ...FIRST, title: "River loggers" })).toBe("River loggers");
  });

  it("falls back to when the project was started when it has no conversation", () => {
    expect(projectName({ ...FIRST, conversations: [] })).toMatch(/^Project started /);
  });
});
