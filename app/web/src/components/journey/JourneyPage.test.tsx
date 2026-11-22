import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import flowFixture from "../../../fixtures/process-flow.json";
import { FlowApiContext } from "../../flow/api";
import type { ProcessFlow, ProjectProgress, StepMark } from "../../flow/types";
import { type ProjectApi, ProjectApiContext } from "../../project/api";
import { projectProgress } from "../../test/api";
import { JourneyPage } from "./JourneyPage";

const FLOW = flowFixture as ProcessFlow;
const STEP = FLOW.phases.flatMap((p) => p.steps).find((s) => !s.out_of_scope);
if (!STEP) throw new Error("the fixture has no step in scope");

function fakeApi(progress: ProjectProgress, markStep: ProjectApi["markStep"]): ProjectApi {
  return {
    progress: () => Promise.resolve(progress),
    markStep,
    documents: () =>
      Promise.resolve({ project_id: "p", documents: [], review: {} } as never),
  } as unknown as ProjectApi;
}

function renderPage(api: ProjectApi, query = "") {
  return render(
    <FlowApiContext.Provider value={{ get: () => Promise.resolve(FLOW) }}>
      <ProjectApiContext.Provider value={api}>
        <JourneyPage projectId="p" query={query} />
      </ProjectApiContext.Provider>
    </FlowApiContext.Provider>,
  );
}

describe("JourneyPage", () => {
  it("draws every phase as a list and every step as a button that says its state", async () => {
    const progress: ProjectProgress = projectProgress({ entry: 1, steps: {}, suggested: STEP.id });
    const { container } = renderPage(fakeApi(progress, () => Promise.resolve(progress)));
    const phases = await screen.findByRole("list", { name: "The phases in order" });
    expect(phases.children).toHaveLength(FLOW.phases.length);
    expect(
      screen.getByRole("button", { name: new RegExp(`^${STEP.label}: .*suggested next`) }),
    ).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("ends with a key to the map's marks, named as a region", async () => {
    const progress: ProjectProgress = projectProgress({ entry: 1, steps: {}, suggested: null });
    const { container } = renderPage(fakeApi(progress, () => Promise.resolve(progress)));
    const legend = await screen.findByRole("region", { name: "How to read the map" });
    expect(legend.querySelectorAll("li").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("opens a step's details and marks it through the server, showing what it answers", async () => {
    const before: ProjectProgress = projectProgress({ entry: 1, steps: {}, suggested: null });
    const after: ProjectProgress = projectProgress({
      entry: 1,
      steps: { [STEP.id]: "done" },
      suggested: null,
      reasons: { [STEP.id]: { state: "done", source: "marked", event: "step_marked" } },
    });
    const marks: [string, StepMark][] = [];
    renderPage(
      fakeApi(before, (_project, stepId, mark) => {
        marks.push([stepId, mark]);
        return Promise.resolve(after);
      }),
      `step=${STEP.id}`,
    );
    const panel = await screen.findByRole("region", { name: STEP.label });
    expect(panel).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mark done" }));
    expect(marks).toEqual([[STEP.id, "done"]]);
    expect(await screen.findByText("You marked this done.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open again" })).toBeInTheDocument();
  });

  it("strikes through an out-of-scope step that was skipped, and leaves the others", async () => {
    const steps = FLOW.phases.flatMap((p) => p.steps);
    const skipped = steps.find((s) => s.out_of_scope);
    const other = steps.find((s) => !s.out_of_scope && s.id !== STEP.id);
    if (!skipped || !other) throw new Error("the fixture has no out-of-scope step");
    const progress: ProjectProgress = projectProgress({
      entry: 1,
      steps: { [skipped.id]: "skipped" },
      suggested: null,
      reasons: {
        [skipped.id]: {
          state: "skipped",
          source: "intake",
          event: "intake_answered",
          question_id: "intake.dmp",
        },
      },
    });
    renderPage(fakeApi(progress, () => Promise.resolve(progress)));
    const stop = await screen.findByRole("button", { name: new RegExp(`^${skipped.label}: `) });
    expect(stop.closest("li")).toHaveClass("is-out-of-scope", "is-skipped");
    const open = screen.getByRole("button", { name: new RegExp(`^${other.label}: `) });
    expect(open.closest("li")).not.toHaveClass("is-out-of-scope");
    expect(open.closest("li")).not.toHaveClass("is-skipped");
  });
});
