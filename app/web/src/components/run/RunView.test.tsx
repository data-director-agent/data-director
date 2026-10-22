import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ReactNode } from "react";

import reference from "../../../fixtures/agents.json";
import abstained from "../../../fixtures/run-abstained.json";
import succeeded from "../../../fixtures/run-succeeded.json";
import empty from "../../../../config/examples/empty.profile.json";
import soil from "../../../../config/examples/soil-chemistry.profile.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import { type RunApi, RunApiContext, RunRefused } from "../../run/api";
import type { RunResult, RunRow } from "../../run/types";
import { AgentDetail } from "../agent/AgentDetail";
import { RunHistory } from "../history/RunHistory";
import { Outcome } from "./Outcome";
import { RunView } from "./RunView";

function defined<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`no ${what}`);
  return value;
}

const standards = defined(normalise(reference as unknown as RawAgentsResponse).agents[0], "agent");
const SUCCEEDED = succeeded as unknown as RunResult;
const ABSTAINED = abstained as unknown as RunResult;
const EXAMPLES = [
  { name: "empty.profile", schema_class: "DatasetProfile", input: empty },
  { name: "soil-chemistry.profile", schema_class: "DatasetProfile", input: soil },
];

function fakeApi(overrides: Partial<RunApi> = {}): RunApi & { started: unknown[] } {
  const started: unknown[] = [];
  return {
    started,
    start: (_agent, input) => {
      started.push(input);
      return Promise.resolve(SUCCEEDED);
    },
    list: () => Promise.resolve([]),
    get: () => Promise.resolve(SUCCEEDED),
    examples: () => Promise.resolve(EXAMPLES),
    ...overrides,
  };
}

function withApi(api: RunApi, children: ReactNode) {
  return <RunApiContext.Provider value={api}>{children}</RunApiContext.Provider>;
}

describe("RunView", () => {
  it("runs an example and moves focus to the outcome", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    const { container } = render(withApi(api, <RunView agent={standards} />));

    await user.click(await screen.findByRole("button", { name: "Load example: soil chemistry profile" }));
    expect(screen.getByLabelText("Title")).toHaveValue(soil.title);
    await user.click(screen.getByRole("button", { name: "Run" }));

    const heading = await screen.findByRole("heading", { name: "Outcome: Succeeded" });
    expect(heading).toHaveFocus();
    expect(api.started).toEqual([soil]);
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Run finished: Succeeded.");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the result with derivation badges and links to the evidence it rests on", async () => {
    const user = userEvent.setup();
    render(withApi(fakeApi(), <RunView agent={standards} />));
    await user.click(screen.getByRole("button", { name: "Run" }));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("Keyword rules").length).toBeGreaterThan(0);
    const link = defined(within(table).getAllByRole("link")[0], "link");
    const target = document.getElementById(defined(link.getAttribute("href"), "href").slice(1));
    expect(target).not.toBeNull();
    const evidence = screen.getByRole("region", { name: "Evidence (14)" });
    expect(within(evidence).getByText("sources: 14 verified, 0 unresolved")).toBeVisible();
    expect(within(evidence).getAllByRole("listitem").length).toBeGreaterThanOrEqual(14);
    expect(screen.getByText(/Changes an agent proposes will wait here/)).toBeVisible();
  });

  it("says what an abstention means and offers to edit the input", async () => {
    const user = userEvent.setup();
    render(withApi(fakeApi({ start: () => Promise.resolve(ABSTAINED) }), <RunView agent={standards} />));
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("heading", { name: "Outcome: Abstained" })).toHaveFocus();
    expect(screen.getByText(/does not give it enough to work with/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Edit the input and run again" }));
    expect(screen.getByRole("heading", { name: "Input: dataset profile" })).toHaveFocus();
  });

  it("reports a refused request as an alert", async () => {
    const user = userEvent.setup();
    const refused = new RunRefused({
      type: "https://w3id.org/data-director/problems/request-refused",
      title: "Data Director could not start this run",
      detail: "unknown agent",
    });
    render(withApi(fakeApi({ start: () => Promise.reject(refused) }), <RunView agent={standards} />));
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown agent");
  });

  it("checks the input before running, and links each error to its field", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(withApi(api, <RunView agent={standards} />));
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.click(screen.getByRole("button", { name: "Run" }));
    const summary = await screen.findByRole("alert");
    expect(summary).toHaveFocus();
    expect(within(summary).getByRole("link", { name: "Enter name of field 1" })).toBeVisible();
    expect(api.started).toEqual([]);
  });

  it("edits the input as JSON and back", async () => {
    const user = userEvent.setup();
    render(withApi(fakeApi(), <RunView agent={standards} />));
    await user.type(screen.getByLabelText("Title"), "Peat");
    await user.click(screen.getByRole("button", { name: "Edit as JSON" }));
    expect(screen.getByLabelText("Input as JSON")).toHaveValue(
      JSON.stringify({ schema_class: "DatasetProfile", title: "Peat" }, null, 2),
    );
    await user.click(screen.getByRole("button", { name: "Edit as a form" }));
    expect(screen.getByLabelText("Title")).toHaveValue("Peat");
  });
});

describe("Outcome", () => {
  it.each([
    ["referred", { status: "referred", reason_code: "requires_human_judgement", referred_to: "data_steward", statement: "Needs a person." }],
    ["suspended", { status: "suspended", statement: "Waiting." }],
  ] as const)("draws a %s run with no axe violations", async (_name, outcome) => {
    const run = structuredClone(ABSTAINED);
    run.envelope.outcome = { ...outcome };
    const { container } = render(<Outcome result={run} agent={standards} idPrefix="t" />);
    expect(screen.getByRole("heading", { level: 3 })).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a failure's problem and the run id to give a steward", () => {
    const run = structuredClone(ABSTAINED);
    run.envelope.outcome = { status: "failed", statement: "Output withheld." };
    run.envelope.problem = {
      type: "https://w3id.org/data-director/problems/grounding-violation",
      title: "Grounding violation",
      detail: "G2: cited an unretrieved record",
    };
    render(<Outcome result={run} agent={standards} idPrefix="t" />);
    expect(screen.getByRole("heading", { name: "Outcome: Failed" })).toBeVisible();
    expect(screen.getByText("G2: cited an unretrieved record")).toBeVisible();
    expect(screen.getByText("grounding-violation")).toBeVisible();
    expect(screen.getByRole("button", { name: "Copy run id" })).toBeVisible();
  });
});

describe("RunHistory", () => {
  const rows: RunRow[] = [
    {
      invocation_id: SUCCEEDED.envelope.invocation_id,
      agent_id: standards.id,
      status: "succeeded",
      completed_at: "2026-01-01T00:00:00Z",
      acting_for: "Josiah Carberry",
    },
    { ...ABSTAINED.envelope, status: "abstained", acting_for: null } as unknown as RunRow,
    { invocation_id: "x", agent_id: "other.agent", status: "failed", completed_at: "", acting_for: null },
  ];

  it("lists this agent's runs and reopens one", async () => {
    const user = userEvent.setup();
    const api = fakeApi({ list: () => Promise.resolve(rows) });
    const { container } = render(withApi(api, <RunHistory agent={standards} />));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(await axe(container)).toHaveNoViolations();

    await user.click(defined(within(table).getAllByRole("button", { name: /^Open/ })[0], "button"));
    expect(await screen.findByRole("heading", { name: "Outcome: Succeeded" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Back to all runs" }));
    expect(await screen.findByRole("heading", { name: "Runs of this agent" })).toBeVisible();
  });

  it("says when there are no runs yet", async () => {
    render(withApi(fakeApi(), <RunHistory agent={standards} />));
    expect(await screen.findByText("No runs yet. Start one from Run.")).toBeVisible();
  });
});

describe("AgentDetail", () => {
  it("opens on Run, and keeps a run while About is shown", async () => {
    const user = userEvent.setup();
    render(withApi(fakeApi(), <AgentDetail agent={standards} />));
    expect(screen.getByRole("tab", { name: "Run" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByRole("heading", { name: "Outcome: Succeeded" });

    await user.click(screen.getByRole("tab", { name: "About" }));
    expect(screen.getByRole("heading", { name: "Can this deployment run it?" })).toBeVisible();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Run" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Outcome: Succeeded" })).toBeVisible();
  });
});
