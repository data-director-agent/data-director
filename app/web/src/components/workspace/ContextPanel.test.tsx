import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import projects from "../../../fixtures/projects.json";
import type { ProjectSummary } from "../../project/api";
import { ContextPanel } from "./ContextPanel";

// A project as the server lists it (app/tests/test_app.py), which has chosen no repository.
const [listed] = projects as unknown as ProjectSummary[];
if (!listed) throw new Error("the fixture lists no project");

function repositoryRow(): HTMLElement {
  const term = screen.getByText("Repository", { selector: "dt" });
  const value = term.nextElementSibling;
  if (!(value instanceof HTMLElement)) throw new Error("the repository row has no value");
  return value;
}

describe("ContextPanel", () => {
  it("says how to choose a repository when none has been", () => {
    render(<ContextPanel project={listed} />);
    expect(repositoryRow()).toHaveTextContent(/None chosen yet/);
  });

  it("names the repository chosen last, its warnings and how to change it", async () => {
    const project: ProjectSummary = {
      ...listed,
      repository: {
        re3data_id: "r3d100010468",
        repository_name: "Zenodo",
        warnings: ["the deployment has no override for Zenodo"],
        chosen_at: "2026-11-07T12:00:00Z",
      },
    };
    const { container } = render(<ContextPanel project={project} />);
    const row = repositoryRow();
    expect(row).toHaveTextContent("Zenodo (re3data r3d100010468)");
    expect(screen.getByRole("list", { name: "What this choice does not check" })).toHaveTextContent(
      "the deployment has no override for Zenodo",
    );
    expect(row).toHaveTextContent("To change it, choose another from a shortlist.");
    expect(row).not.toHaveTextContent("Not built yet");
    expect(await axe(container)).toHaveNoViolations();
  });
});
