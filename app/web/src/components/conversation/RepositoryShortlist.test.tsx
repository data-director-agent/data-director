import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/repository-chosen.json";
import { type ProjectApi, ProjectApiContext, type RepositoryRequirements, httpProjectApi } from "../../project/api";
import { shortlistOf } from "../../project/shortlist";
import { shortlistRun } from "../../test/shortlist";
import { RunRefused } from "../../run/api";
import { RepositoryShortlist } from "./RepositoryShortlist";

// What the server says after ORDA is chosen (app/tests/test_repository_choice.py).
const ORDA_CHOSEN = fixture as RepositoryRequirements;
const PROJECT = "0192f3a4-0000-7000-8000-000000000001";

function renderShortlist(chooseRepository: ProjectApi["chooseRepository"], chosenId: string | null = null) {
  const onChosen = vi.fn();
  const api: ProjectApi = { ...httpProjectApi, chooseRepository };
  const view = render(
    <ProjectApiContext.Provider value={api}>
      <RepositoryShortlist
        projectId={PROJECT}
        shortlist={shortlistOf(shortlistRun())}
        chosenId={chosenId}
        idPrefix="shortlist-test"
        onChosen={onChosen}
      />
    </ProjectApiContext.Provider>,
  );
  return { onChosen, ...view };
}

describe("RepositoryShortlist", () => {
  it("sends only the re3data identifier and shows what the choice resolved to", async () => {
    const choose = vi.fn<ProjectApi["chooseRepository"]>().mockResolvedValue(ORDA_CHOSEN);
    const { onChosen, container } = renderShortlist(choose);
    expect(screen.getByRole("heading", { name: "Repositories shortlisted" })).toBeVisible();
    expect(screen.getByRole("link", { name: "r3d100012124" })).toHaveAttribute(
      "href",
      "https://doi.org/10.17616/R3D100012124",
    );
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    expect(choose).toHaveBeenCalledWith(PROJECT, "r3d100012124");
    expect(onChosen).toHaveBeenCalledWith(ORDA_CHOSEN);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(`${ORDA_CHOSEN.repository_name} is the project's repository.`);
    expect(status).toHaveTextContent("Checked against datacite-4@v1 and orda@v2.");
    expect(status).toHaveTextContent("A deposit needs a metadata record.");
    expect(status).toHaveTextContent("It should also have a README and a data dictionary.");
    expect(status).toHaveTextContent(/Its metadata must give: Title, Authors/);
    expect(screen.queryByRole("button", { name: "Choose ORDA" })).toBeNull();
    expect(screen.getByRole("button", { name: "Choose r3d100010468" })).toBeEnabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks the repository already chosen and shows the warnings of a new choice", async () => {
    const zenodo: RepositoryRequirements = {
      ...ORDA_CHOSEN,
      re3data_id: "r3d100010468",
      repository_name: "Zenodo",
      requirement_sets: [{ ref: "datacite-4@v1", sha256: "e".repeat(64) }],
      warnings: ["the deployment has no override for Zenodo"],
    };
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>().mockResolvedValue(zenodo), "r3d100012124");
    const orda = screen.getByRole("listitem", { current: true });
    expect(orda).toHaveTextContent("Chosen");
    await userEvent.click(screen.getByRole("button", { name: "Choose r3d100010468" }));
    expect(screen.getByRole("list", { name: "What this choice does not check" })).toHaveTextContent(
      "the deployment has no override for Zenodo",
    );
    expect(screen.getByRole("listitem", { current: true })).toHaveTextContent("r3d100010468");
    expect(screen.getByRole("button", { name: "Choose ORDA" })).toBeEnabled();
  });

  it("says why a choice was refused and records nothing", async () => {
    const refused = new RunRefused({
      type: "https://data-director.example/problems/request-refused",
      title: "Data Director could not record this repository",
      detail: "the pinned re3data export holds no repository r3d100012124",
    });
    const { onChosen } = renderShortlist(vi.fn<ProjectApi["chooseRepository"]>().mockRejectedValue(refused));
    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/could not record ORDA as your repository/);
    expect(onChosen).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Choose ORDA" })).toBeEnabled();
  });
});
