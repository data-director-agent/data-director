import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import offeredFixture from "../../../fixtures/orcid-record.json";
import keptFixture from "../../../fixtures/project-researchers.json";
import { type ProjectApi, ProjectApiContext, type ResearcherRecord } from "../../project/api";
import { SessionApiContext } from "../../session/api";
import { DEVELOPMENT, fakeSessionApi } from "../../test/session";
import { ResearcherPanel } from "./ResearcherPanel";

// What the server says (app/tests/test_researcher_facts.py): the sample public record, and what
// the person kept of it, as the operator's principal on a development server.
const OFFERED = offeredFixture as ResearcherRecord;
const KEPT = keptFixture as ResearcherRecord[];
const PROJECT = "01900000-0000-7000-8000-000000000001";

function renderPanel(api: Partial<ProjectApi>) {
  const full = {
    researchers: () => Promise.resolve([]),
    orcidRecord: () => Promise.resolve(OFFERED),
    ...api,
  } as unknown as ProjectApi;
  return render(
    <SessionApiContext.Provider value={fakeSessionApi(DEVELOPMENT)}>
      <ProjectApiContext.Provider value={full}>
        <ResearcherPanel projectId={PROJECT} />
      </ProjectApiContext.Provider>
    </SessionApiContext.Provider>,
  );
}

describe("ResearcherPanel", () => {
  it("offers the person's record with nothing ticked, and sends only what they tick", async () => {
    const keepResearcher = vi.fn(() => Promise.resolve(KEPT));
    const { container } = renderPanel({ keepResearcher });
    const user = userEvent.setup();
    expect(await screen.findByText(/No researcher has kept/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Bring in facts from your ORCID record/ }));
    const form = await screen.findByRole("form", { name: "Choose what to keep" });
    const boxes = within(form).getAllByRole("checkbox");
    expect(boxes.length).toBeGreaterThan(0);
    expect(boxes.every((box) => !(box as HTMLInputElement).checked)).toBe(true);
    expect(form).not.toHaveTextContent("@");
    expect(await axe(container)).toHaveNoViolations();

    await user.click(within(form).getByRole("checkbox", { name: /^Keywords:/ }));
    const employment = OFFERED.affiliations?.[0];
    const affiliations = within(form).getByRole("group", { name: "Affiliations" });
    await user.click(within(affiliations).getAllByRole("checkbox")[0] as HTMLElement);
    await user.click(within(form).getByRole("button", { name: "Keep the ticked facts" }));

    expect(keepResearcher).toHaveBeenCalledWith(PROJECT, {
      sections: ["keywords"],
      affiliations: [employment?.put_code],
      works: [],
      fundings: [],
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Kept.");
    expect(screen.getByRole("heading", { name: /Josiah Carberry/, level: 3 })).toBeVisible();
  });

  it("ticks all of a section at once", async () => {
    renderPanel({});
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bring in facts/ }));
    const works = await screen.findByRole("group", { name: "Works" });
    await user.click(within(works).getByRole("button", { name: /Tick all/ }));
    expect(
      within(works)
        .getAllByRole("checkbox")
        .every((box) => (box as HTMLInputElement).checked),
    ).toBe(true);
  });

  it("lets the person withdraw only what they kept", async () => {
    const withdrawResearcher = vi.fn(() => Promise.resolve([]));
    renderPanel({ researchers: () => Promise.resolve(KEPT), withdrawResearcher });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Withdraw what you kept" }));
    expect(withdrawResearcher).toHaveBeenCalledWith(PROJECT);
    expect(await screen.findByRole("status")).toHaveTextContent("no longer given");
  });

  it("shows no withdraw button for another researcher's record", async () => {
    const someone = { ...KEPT[0], orcid_id: "https://orcid.org/0000-0002-1694-233X" };
    renderPanel({ researchers: () => Promise.resolve([someone as ResearcherRecord]) });
    expect(await screen.findByRole("heading", { level: 3 })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Withdraw/ })).toBeNull();
  });

  it("says when the ORCID record cannot be read", async () => {
    renderPanel({ orcidRecord: () => Promise.reject(new Error("ORCID could not be reached")) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bring in facts/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ORCID could not be reached");
  });
});
