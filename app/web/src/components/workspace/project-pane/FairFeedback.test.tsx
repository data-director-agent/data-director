import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { ProjectDocument } from "../../../project/api";
import { ASK_FOR_FEEDBACK, type FairnessReport } from "../../../project/fairness";
import { ProjectRunsApiContext } from "../../../project/projectRuns";
import type { Envelope } from "../../../run/types";
import { aReport, aRun, meeting, runsApi } from "../../../test/fairness";
import { PROJECT, at } from "../../../test/projectApi";
import { FairFeedback } from "./FairFeedback";

const PROJECT_ID = "01900000-0000-7000-8000-0000000000aa";
const RECORD_ID = "01900000-0000-7000-8000-00000000000a";

function aRecord(versions: number): ProjectDocument {
  const template = at(PROJECT.documents, 0);
  const version = at(template.versions, 0);
  return {
    ...template,
    document_id: RECORD_ID,
    document_kind: "metadata_record",
    versions: Array.from({ length: versions }, (_, n) => ({
      ...version,
      document_id: RECORD_ID,
      version: n + 1,
    })),
  };
}

function assessed(report: FairnessReport, version: number): FairnessReport {
  return { ...report, assessed_version: { document_id: RECORD_ID, version } };
}

function renderPane(
  runs: Envelope[],
  documents: ProjectDocument[],
  onAsk = vi.fn(),
) {
  const view = render(
    <ProjectRunsApiContext.Provider value={runsApi(runs)}>
      <FairFeedback
        projectId={PROJECT_ID}
        documents={documents}
        onAsk={onAsk}
      />
    </ProjectRunsApiContext.Provider>,
  );
  return { ...view, onAsk };
}

function pane(): HTMLElement {
  return screen.getByRole("region", { name: "How FAIR it is" });
}

describe("FairFeedback, beside the conversation", () => {
  it("shows the count met for each principle as words and a meter, never colour alone", async () => {
    const { container } = renderPane(
      [aRun(assessed(aReport(), 1), "2026-01-02T00:00:00Z")],
      [aRecord(1)],
    );
    const meters = await within(pane()).findAllByRole("meter");
    expect(meters.length).toBeGreaterThan(0);
    for (const meter of meters)
      expect(meter).toHaveAccessibleName(/\d+ of \d+ checks met/);
    expect(pane()).toHaveTextContent(/Checked at deposit/);
    expect(pane()).toHaveTextContent(/Not a FAIRness evaluation/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("puts a question about a next step, or about checking again, in the message box", async () => {
    const user = userEvent.setup();
    const { onAsk } = renderPane(
      [aRun(assessed(aReport(), 1), "2026-01-02T00:00:00Z")],
      [aRecord(1)],
    );
    const next = await within(pane()).findByRole("region", {
      name: "What to do next",
    });
    const [first] = within(next).getAllByRole("button", { name: "Ask how" });
    await user.click(first as HTMLElement);
    expect(onAsk).toHaveBeenLastCalledWith(
      expect.stringContaining(
        aReport().checks.find((c) => !c.met)?.recommendation ?? "",
      ),
    );
    await user.click(
      within(pane()).getByRole("button", { name: "Check again" }),
    );
    expect(onAsk).toHaveBeenLastCalledWith(ASK_FOR_FEEDBACK);
  });

  it("says what is newly met since the check before, and where a count went up", async () => {
    const before = aReport();
    const [first] = before.next_steps as [string];
    const runs = [
      aRun(
        assessed(meeting(before, first), 2),
        "2026-01-03T00:00:00Z",
        "later",
      ),
      aRun(assessed(before, 1), "2026-01-02T00:00:00Z", "earlier"),
    ];
    renderPane(runs, [aRecord(2)]);
    const gained = await within(pane()).findByRole("region", {
      name: "Newly met since the last check",
    });
    expect(within(gained).getAllByRole("listitem")).toHaveLength(1);
    expect(pane()).toHaveTextContent(/up from/);
  });

  it("asks for the new version to be checked once the record has changed since", async () => {
    const user = userEvent.setup();
    const { onAsk } = renderPane(
      [aRun(assessed(aReport(), 1), "2026-01-02T00:00:00Z")],
      [aRecord(3)],
    );
    expect(await within(pane()).findByRole("note")).toHaveTextContent(
      /version 3/,
    );
    await user.click(
      within(pane()).getByRole("button", { name: "Check the new version" }),
    );
    expect(onAsk).toHaveBeenLastCalledWith(ASK_FOR_FEEDBACK);
  });

  it("with no report yet, offers the first check only once there is a record to check", async () => {
    const { unmount } = renderPane([], []);
    expect(
      await within(pane()).findByText(
        /Once the project has a draft metadata record/,
      ),
    ).toBeVisible();
    expect(within(pane()).queryByRole("button")).not.toBeInTheDocument();
    unmount();
    const { onAsk } = renderPane([], [aRecord(1)]);
    await userEvent
      .setup()
      .click(
        await within(pane()).findByRole("button", { name: "How FAIR is it?" }),
      );
    expect(onAsk).toHaveBeenCalledWith(ASK_FOR_FEEDBACK);
  });
});
