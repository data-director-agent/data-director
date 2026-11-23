import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import flowFixture from "../../../fixtures/process-flow.json";
import factsFixture from "../../../fixtures/project-facts.json";
import documentsFixture from "../../../fixtures/project-documents.json";
import projects from "../../../fixtures/projects.json";
import type { ProcessFlow, ProjectProgress } from "../../flow/types";
import type { ProjectDocuments, ProjectSummary } from "../../project/api";
import { type FactsApi, FactsApiContext, type ProjectFacts, factKey } from "../../project/facts";
import { ProjectRunsApiContext } from "../../project/projectRuns";
import { aReport, aRun, runsApi } from "../../test/fairness";
import { ContextPanel } from "./ContextPanel";

// A project as the server lists it (app/tests/test_app.py), which has chosen no repository.
const [listed] = projects as unknown as ProjectSummary[];
if (!listed) throw new Error("the fixture lists no project");
const PROJECT_ID = listed.project_id;
const FLOW = flowFixture as unknown as ProcessFlow;
const OFFERED = factsFixture as unknown as ProjectFacts;
const NO_FACTS: ProjectFacts = { decisions: [], proposals: [] };
const DOCUMENTS = (documentsFixture as unknown as ProjectDocuments).documents;
const SETTLED: ProjectSummary = { ...listed, intake: "complete" };

function renderPanel(props: Parameters<typeof ContextPanel>[0], facts: ProjectFacts = NO_FACTS) {
  const api: FactsApi = {
    facts: () => Promise.resolve(facts),
    decideFact: () => Promise.reject(new Error("the pane decides nothing")),
  };
  return render(
    <FactsApiContext.Provider value={api}>
      <ProjectRunsApiContext.Provider value={runsApi([aRun(aReport(), "2026-01-02T00:00:00Z")])}>
        <ContextPanel {...props} />
      </ProjectRunsApiContext.Provider>
    </FactsApiContext.Provider>,
  );
}

function region(name: string | RegExp): HTMLElement {
  return screen.getByRole("region", { name });
}

describe("ContextPanel", () => {
  it("before a project, says the first message starts one and draws nothing of a project", () => {
    renderPanel({});
    expect(screen.getByRole("region", { name: "Project" })).toHaveTextContent(/first message starts a new project/);
    expect(screen.queryByRole("region", { name: /^Waiting on you/ })).not.toBeInTheDocument();
    expect(region("Guardrails")).toBeInTheDocument();
  });

  it("puts what waits on the person first, each row with what to do about it", async () => {
    const onAsk = vi.fn();
    const project: ProjectSummary = {
      ...listed,
      repository: {
        repository_id: "r3d100010468",
        re3data_id: "r3d100010468",
        repository_name: "Zenodo",
        warnings: ["the deployment has no override for Zenodo"],
        chosen_at: "2026-11-07T12:00:00Z",
      },
    };
    const { container } = renderPanel(
      {
        projectId: PROJECT_ID,
        project,
        documents: { state: "loaded", documents: DOCUMENTS },
        onAsk,
      },
      OFFERED,
    );
    const sections = screen.getAllByRole("heading", { level: 3 }).map((h) => h.id);
    expect(sections[0]).toBe("waiting-heading");

    const waiting = await screen.findByRole("list", {
      name: /^Waiting on you/,
    });
    const factLinks = await within(waiting).findAllByRole("link", {
      name: /^Review .+/,
    });
    // The proposed document goes to its review; the approved one does not wait.
    const reviews = within(waiting).getAllByRole("link", { name: "Review" });
    expect(reviews).toHaveLength(1);
    expect(reviews[0]).toHaveAttribute("href", expect.stringContaining("?doc="));
    // One row per kind of fact proposed, each landing on its own proposals on the facts page.
    const proposed = new Set(OFFERED.proposals.map((p) => factKey(p.fact)));
    expect(factLinks).toHaveLength(new Set(OFFERED.proposals.map((p) => p.fact.fact_kind)).size);
    for (const link of factLinks) {
      const href = new URL(link.getAttribute("href") ?? "", location.origin);
      expect(href.pathname).toBe(`/projects/${PROJECT_ID}/facts`);
      const named = href.searchParams.getAll("fact");
      expect(named.length).toBeGreaterThan(0);
      for (const key of named) expect(proposed).toContain(key);
    }
    // A repository warning is asked about in the conversation, not decided here.
    await userEvent.click(within(waiting).getByRole("button", { name: "Ask why" }));
    expect(onAsk).toHaveBeenCalledWith(expect.stringContaining("the deployment has no override for Zenodo"));
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when nothing waits on the person", async () => {
    renderPanel({
      projectId: PROJECT_ID,
      project: SETTLED,
      documents: { state: "loaded", documents: [] },
    });
    const waiting = region(/^Waiting on you/);
    expect(within(waiting).queryByRole("list")).not.toBeInTheDocument();
    expect(await within(waiting).findByText(/Nothing waits on you/)).toBeVisible();
  });

  it("names the step suggested next and starts a new conversation about it", async () => {
    const onStartStep = vi.fn();
    const step = FLOW.phases[1]?.steps[0];
    if (!step) throw new Error("the flow fixture has no step");
    const progress: ProjectProgress = {
      ...(listed.progress as ProjectProgress),
      suggested: step.id,
    };
    renderPanel({
      projectId: PROJECT_ID,
      project: SETTLED,
      flow: { state: "loaded", flow: FLOW },
      progress,
      onStartStep,
    });
    const where = region("Where we are");
    expect(within(where).getByText("Suggested next").nextElementSibling).toHaveTextContent(step.label);
    await userEvent.click(within(where).getByRole("button", { name: "Ask about the next step" }));
    expect(onStartStep).toHaveBeenCalledWith(step);
  });

  it("shows what Data Director works from, each fact marked proposed, the unknown named together", async () => {
    renderPanel({ projectId: PROJECT_ID, project: SETTLED }, OFFERED);
    const working = region("What Data Director is working from");
    const sensitivity = (await within(working).findByText("Sensitive data")).nextElementSibling;
    expect(sensitivity).toHaveTextContent("Proposed");
    // Each value links to that fact on the facts page.
    const [proposal] = OFFERED.proposals.filter((p) => p.fact.fact_kind === "sensitivity");
    if (!proposal) throw new Error("the fixture proposes no sensitivity");
    const value = within(sensitivity as HTMLElement).getByRole("link");
    expect(new URL(value.getAttribute("href") ?? "", location.origin).searchParams.getAll("fact")).toEqual([
      factKey(proposal.fact),
    ]);
    // What nothing is known of is named in one row.
    expect(within(working).getByText("Not known yet").nextElementSibling).toHaveTextContent("Funder");
    expect(within(working).getByText("Repository chosen").nextElementSibling).toHaveTextContent(/None chosen yet/);
    expect(within(working).getByRole("link", { name: /^Open Project facts/ })).toHaveAttribute(
      "href",
      `/projects/${PROJECT_ID}/facts`,
    );
  });

  it("draws the guardrails that are not built, each linked to its issues", () => {
    renderPanel({});
    const guardrails = region("Guardrails");
    const badges = within(guardrails).getAllByText("Not built yet");
    expect(badges.length).toBeGreaterThan(0);
    for (const badge of badges) {
      expect(within(badge.parentElement as HTMLElement).getAllByRole("link").length).toBeGreaterThan(0);
    }
  });

  it("shows how FAIR the metadata record is only where an agent here gives FAIR feedback", async () => {
    const { unmount } = renderPanel({
      projectId: PROJECT_ID,
      documents: { state: "loaded", documents: DOCUMENTS },
    });
    expect(screen.queryByRole("region", { name: "How FAIR it is" })).not.toBeInTheDocument();
    unmount();
    renderPanel({
      projectId: PROJECT_ID,
      documents: { state: "loaded", documents: DOCUMENTS },
      fairFeedback: true,
    });
    const fair = region("How FAIR it is");
    expect((await within(fair).findAllByRole("meter")).length).toBeGreaterThan(0);
    expect(within(fair).getByRole("link", { name: "Every check" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT_ID}/fair`,
    );
  });
});
