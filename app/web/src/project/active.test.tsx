import { render, screen, waitFor } from "@testing-library/react";

import { setPreference } from "../preferences";
import { ActiveProjectProvider, useActiveProject } from "./active";
import { type ProjectApi, type ProjectSummary, ProjectApiContext } from "./api";

const PROJECT = "0190a5b2-0000-7000-8000-000000000001";

function Shown() {
  return <output>{useActiveProject().projectId ?? "none"}</output>;
}

function renderActive() {
  const api = {
    projects: () => Promise.resolve([{ project_id: PROJECT } as ProjectSummary]),
  } as unknown as ProjectApi;
  return render(
    <ProjectApiContext.Provider value={api}>
      <ActiveProjectProvider>
        <Shown />
      </ActiveProjectProvider>
    </ProjectApiContext.Provider>,
  );
}

afterEach(() => localStorage.clear());

describe("ActiveProjectProvider", () => {
  it("returns to the project used last", async () => {
    localStorage.setItem("dd-project", PROJECT);
    renderActive();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(PROJECT));
  });

  it("starts with none chosen where the person prefers, still remembering the last", async () => {
    localStorage.setItem("dd-project", PROJECT);
    setPreference("startupProject", "none");
    renderActive();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("none"));
    expect(localStorage.getItem("dd-project")).toBe(PROJECT);
  });
});
