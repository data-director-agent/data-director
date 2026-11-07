import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/projects.json";
import { type ProjectApi, type ProjectSummary, ProjectApiContext } from "../../project/api";
import { projectName } from "../../project/name";
import { ProjectsPage } from "./ProjectsPage";

// What the server says (app/tests/test_app.py): one untitled project with an inventory of one
// file and one conversation, "My logger data".
const PROJECTS = fixture as ProjectSummary[];
const FIRST = PROJECTS[0] as ProjectSummary;

function renderPage(projects: ProjectApi["projects"]) {
  const api = { projects, documents: vi.fn(), disclosure: vi.fn(), decide: vi.fn() };
  return render(
    <ProjectApiContext.Provider value={api as unknown as ProjectApi}>
      <ProjectsPage />
    </ProjectApiContext.Provider>,
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

  it("says how to start a project when there is none", async () => {
    renderPage(() => Promise.resolve([]));
    expect(await screen.findByText(/You have no project yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new conversation" })).toHaveAttribute(
      "href",
      "/",
    );
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
