import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/repository-chosen.json";
import {
  type ProjectApi,
  ProjectApiContext,
  type RepositoryRequirements,
  httpProjectApi,
} from "../../project/api";
import { shortlistOf, unlistedOf } from "../../project/shortlist";
import { shortlistRun } from "../../test/shortlist";
import { RunRefused } from "../../run/api";
import { RepositoryShortlist, feeWording } from "./RepositoryShortlist";

// What the server says after ORDA is chosen (app/tests/test_repository_choice.py).
const ORDA_CHOSEN = fixture as RepositoryRequirements;
const PROJECT = "0192f3a4-0000-7000-8000-000000000001";

function renderShortlist(
  chooseRepository: ProjectApi["chooseRepository"],
  chosenId: string | null = null,
  shortlist = shortlistOf(shortlistRun()),
  extra: { unlisted?: ReturnType<typeof unlistedOf>; planAttached?: boolean } = {},
) {
  const onChosen = vi.fn();
  const api: ProjectApi = { ...httpProjectApi, chooseRepository };
  const view = render(
    <ProjectApiContext.Provider value={api}>
      <RepositoryShortlist
        projectId={PROJECT}
        shortlist={shortlist}
        {...extra}
        chosenId={chosenId}
        idPrefix="shortlist-test"
        onChosen={onChosen}
      />
    </ProjectApiContext.Provider>,
  );
  return { onChosen, ...view };
}

describe("RepositoryShortlist", () => {
  it("marks a repository the researcher asked about as such, never as mandated (#1167)", () => {
    const shortlist = shortlistOf(shortlistRun()).map((r) =>
      r.re3dataId === "r3d100010468" ? { ...r, basis: "asked_about" } : r,
    );
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>(), null, shortlist);
    const [orda, zenodo] = screen.getAllByRole("listitem");
    expect(orda).toHaveTextContent("Mandated");
    expect(zenodo).toHaveTextContent("You asked about this");
    expect(zenodo).not.toHaveTextContent("Mandated");
  });

  it("marks a repository the researcher's plan names as such, never as mandated (#1233)", () => {
    const shortlist = shortlistOf(shortlistRun()).map((r) =>
      r.re3dataId === "r3d100010468" ? { ...r, basis: "in_plan" } : r,
    );
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>(), null, shortlist);
    const [, zenodo] = screen.getAllByRole("listitem");
    expect(zenodo).toHaveTextContent("In your plan");
    expect(zenodo).not.toHaveTextContent("Mandated");
  });

  it("shows a plan's repository re3data does not list as the plan's, with nothing to choose (#1334)", async () => {
    const { container } = renderShortlist(vi.fn<ProjectApi["chooseRepository"]>(), null, undefined, {
      unlisted: unlistedOf(shortlistRun()),
    });
    const archive = screen.getAllByRole("listitem").at(-1);
    expect(archive).toHaveTextContent("Netherbrook Local Studies Archive");
    expect(archive).toHaveTextContent("In your plan");
    expect(screen.queryByRole("button", { name: /Netherbrook/ })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("gives a fee re3data does not state as one to check, never as none (#1334)", () => {
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>());
    const [orda, zenodo] = screen.getAllByRole("listitem");
    expect(orda).toHaveTextContent(feeWording("unstated") ?? "missing");
    expect(zenodo).toHaveTextContent(feeWording("yes") ?? "missing");
  });

  it("says a plan's repositories need its commitments confirmed when none is shown (#1334)", () => {
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>(), null, undefined, { planAttached: true });
    expect(screen.getByText(/once you confirm its sharing commitments/)).toBeVisible();
  });

  it("does not ask for the plan's commitments once its repositories are shown", () => {
    renderShortlist(vi.fn<ProjectApi["chooseRepository"]>(), null, undefined, {
      planAttached: true,
      unlisted: unlistedOf(shortlistRun()),
    });
    expect(screen.queryByText(/once you confirm its sharing commitments/)).not.toBeInTheDocument();
  });

  it("sends only the re3data identifier and shows what the choice resolved to", async () => {
    const choose = vi
      .fn<ProjectApi["chooseRepository"]>()
      .mockResolvedValue(ORDA_CHOSEN);
    const { onChosen, container } = renderShortlist(choose);
    expect(
      screen.getByRole("heading", { name: "Repositories shortlisted" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "r3d100012124" })).toHaveAttribute(
      "href",
      "https://doi.org/10.17616/R3D100012124",
    );
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    expect(choose).toHaveBeenCalledWith(PROJECT, "r3d100012124");
    expect(onChosen).toHaveBeenCalledWith(ORDA_CHOSEN);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(
      `${ORDA_CHOSEN.repository_name} is the project's repository.`,
    );
    expect(status).toHaveTextContent(
      "Checked against datacite-4@v1 and orda@v3.",
    );
    expect(status).toHaveTextContent("A deposit needs a metadata record.");
    expect(status).toHaveTextContent(
      "It should also have a README and a data dictionary.",
    );
    expect(status).toHaveTextContent(/Its metadata must give: Title, Authors/);
    expect(screen.queryByRole("button", { name: "Choose ORDA" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Choose r3d100010468" }),
    ).toBeEnabled();
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
    renderShortlist(
      vi.fn<ProjectApi["chooseRepository"]>().mockResolvedValue(zenodo),
      "r3d100012124",
    );
    const orda = screen.getByRole("listitem", { current: true });
    expect(orda).toHaveTextContent("Chosen");
    await userEvent.click(
      screen.getByRole("button", { name: "Choose r3d100010468" }),
    );
    expect(
      screen.getByRole("list", { name: "What this choice does not check" }),
    ).toHaveTextContent("the deployment has no override for Zenodo");
    expect(screen.getByRole("listitem", { current: true })).toHaveTextContent(
      "r3d100010468",
    );
    expect(screen.getByRole("button", { name: "Choose ORDA" })).toBeEnabled();
  });

  it("says why a choice was refused and records nothing", async () => {
    const refused = new RunRefused({
      type: "https://data-director.example/problems/request-refused",
      title: "Data Director could not record this repository",
      detail: "the pinned re3data export holds no repository r3d100012124",
    });
    const { onChosen } = renderShortlist(
      vi.fn<ProjectApi["chooseRepository"]>().mockRejectedValue(refused),
    );
    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      /could not record ORDA as your repository/,
    );
    expect(onChosen).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Choose ORDA" })).toBeEnabled();
  });
});
