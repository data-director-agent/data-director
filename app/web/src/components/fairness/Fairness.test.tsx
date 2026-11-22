import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { type ProjectApi, ProjectApiContext } from "../../project/api";
import { ProjectRunsApiContext } from "../../project/projectRuns";
import type { Envelope } from "../../run/types";
import { aReport, aRun, meeting, runsApi } from "../../test/fairness";
import { fakeProjectApi } from "../../test/projectApi";
import { FairnessPanel } from "./FairnessPanel";

const PROJECT_ID = "01900000-0000-7000-8000-0000000000aa";

describe("FairnessPanel, the project's tab", () => {
  function renderPanel(runs: Envelope[], api: ProjectApi = fakeProjectApi()) {
    return render(
      <ProjectApiContext.Provider value={api}>
        <ProjectRunsApiContext.Provider value={runsApi(runs)}>
          <FairnessPanel projectId={PROJECT_ID} />
        </ProjectRunsApiContext.Provider>
      </ProjectApiContext.Provider>,
    );
  }

  it("lists every check by principle and each stored report as a row", async () => {
    const before = aReport();
    const after = meeting(before, before.next_steps[0] as string);
    const { container } = renderPanel([
      aRun(after, "2026-01-03T00:00:00Z", "later"),
      aRun(before, "2026-01-02T00:00:00Z", "earlier"),
    ]);
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(
      screen.getByRole("region", { name: "Every check" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Ask how" }),
    ).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has a button that opens the conversation with the FAIR question ready", async () => {
    const user = userEvent.setup();
    renderPanel([aRun(aReport(), "2026-01-03T00:00:00Z")]);
    await user.click(await screen.findByRole("button", { name: "Check again" }));
    expect(location.search).toBe("?fair=check");
  });

  it("points on to the deposit checks once every check a draft can meet is met", async () => {
    let report = aReport();
    for (const check of report.checks.filter((c) => !c.met && !c.after_deposit))
      report = meeting(report, check.check);
    renderPanel([aRun(report, "2026-01-03T00:00:00Z")]);
    expect(
      await screen.findByRole("link", { name: "the deposit checks" }),
    ).toHaveAttribute("href", `/projects/${PROJECT_ID}/deposit`);
  });
});
