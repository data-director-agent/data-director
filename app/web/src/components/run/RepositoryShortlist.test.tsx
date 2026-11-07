import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import repositoryFixture from "../../../fixtures/project-repository.json";
import {
  type ProjectApi,
  ProjectApiContext,
  type RepositoryChoice,
  httpProjectApi,
} from "../../project/api";
import { RunRefused } from "../../run/api";
import type { Envelope } from "../../run/types";
import { RepositoryShortlist, candidatesOf } from "./RepositoryShortlist";

// ORDA, chosen from a shortlist (app/tests/test_repository_choice.py).
const ORDA = repositoryFixture as RepositoryChoice;
const PROJECT = "01900000-0000-7000-8000-000000000001";
const RUN = "01900000-0000-7000-8000-000000000002";

/** An `advisor.repository` run in a project, shortlisting ORDA and Zenodo. */
function shortlist(projectId: string | null = PROJECT): Envelope {
  const record = (id: string, name: string) => ({
    source_id: id,
    content: { re3data_id: id, name, metadata_standards: [] },
  });
  return {
    invocation_id: RUN,
    agent_id: "advisor.repository",
    agent_version: "0.1.0",
    completed_at: "2026-01-01T00:00:00Z",
    grounding_mode: "retrieval",
    policy_bundle_ref: "test@v1",
    outcome: { status: "succeeded", statement: "Two candidates." },
    project_id: projectId,
    payload: {
      candidates: [
        { grounded_on: [{ source_id: "r3d100012124" }, { source_id: "FAIRsharing.abc" }] },
        { grounded_on: [{ source_id: "r3d100010468" }] },
      ],
    },
    evidence: [record("r3d100012124", "ORDA"), record("r3d100010468", "Zenodo")],
  };
}

function renderShortlist(envelope: Envelope, chooseRepository: ProjectApi["chooseRepository"]) {
  const api: ProjectApi = { ...httpProjectApi, chooseRepository };
  return render(
    <ProjectApiContext.Provider value={api}>
      <RepositoryShortlist envelope={envelope} idPrefix="run" />
    </ProjectApiContext.Provider>,
  );
}

describe("candidatesOf", () => {
  it("names each candidate from the re3data record it rests on", () => {
    expect(candidatesOf(shortlist())).toEqual([
      { re3dataId: "r3d100012124", name: "ORDA" },
      { re3dataId: "r3d100010468", name: "Zenodo" },
    ]);
  });
});

describe("RepositoryShortlist", () => {
  it("chooses a candidate, sending only the run and its re3data identifier", async () => {
    const choose = vi.fn(() => Promise.resolve(ORDA));
    const { container } = renderShortlist(shortlist(), choose);
    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    expect(choose).toHaveBeenCalledWith(PROJECT, RUN, "r3d100012124");
    expect(await screen.findByRole("status")).toHaveTextContent("ORDA chosen for this project.");
    expect(screen.getByRole("link", { name: "See what it asks for" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT}?doc=repository`,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says each warning the choice resolved with", async () => {
    const warned = { ...ORDA, repository_name: "Zenodo", warnings: ["no override for Zenodo"] };
    renderShortlist(shortlist(), () => Promise.resolve(warned));
    await userEvent.click(screen.getByRole("button", { name: "Choose Zenodo" }));
    expect(await screen.findByRole("status")).toHaveTextContent("no override for Zenodo");
  });

  it("says why a choice was refused, and moves focus to it", async () => {
    const refused = new RunRefused({ type: "about:blank", title: "No", detail: "That run is not in this project." });
    renderShortlist(shortlist(), () => Promise.reject(refused));
    await userEvent.click(screen.getByRole("button", { name: "Choose ORDA" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("That run is not in this project.");
    expect(alert).toHaveFocus();
  });

  it("offers no choice for a run outside a project", () => {
    renderShortlist(shortlist(null), vi.fn());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
