import { render, screen, waitFor } from "@testing-library/react";

import { setPreference } from "../preferences";
import { ActiveProjectProvider, useActiveProject } from "./active";
import { type ProjectApi, type ProjectSummary, ProjectApiContext } from "./api";
import { type StewardApi, StewardApiContext } from "./steward";
import { MEMBER_VIEW, VIEW, fakeStewardApi } from "../test/steward";

const PROJECT = "0190a5b2-0000-7000-8000-000000000001";

function Shown() {
  return <output>{useActiveProject().projectId ?? "none"}</output>;
}

function renderActive(listed: string[] = [PROJECT], steward: StewardApi = fakeStewardApi(MEMBER_VIEW)) {
  const api = {
    projects: () => Promise.resolve(listed.map((project_id) => ({ project_id }) as ProjectSummary)),
  } as unknown as ProjectApi;
  return render(
    <ProjectApiContext.Provider value={api}>
      <StewardApiContext.Provider value={steward}>
        <ActiveProjectProvider>
          <Shown />
        </ActiveProjectProvider>
      </StewardApiContext.Provider>
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

  it("keeps a project the person opened as its data steward, which their list never holds", async () => {
    localStorage.setItem("dd-project", PROJECT);
    const steward = fakeStewardApi(VIEW);
    renderActive([], steward);
    await waitFor(() => expect(steward.view).toHaveBeenCalledWith(PROJECT, expect.anything()));
    expect(screen.getByRole("status")).toHaveTextContent(PROJECT);
    expect(localStorage.getItem("dd-project")).toBe(PROJECT);
  });

  it("forgets a remembered project the server neither lists nor opens for them as its steward", async () => {
    localStorage.setItem("dd-project", PROJECT);
    renderActive([], fakeStewardApi(MEMBER_VIEW));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("none"));
    expect(localStorage.getItem("dd-project")).toBeNull();
  });
});
