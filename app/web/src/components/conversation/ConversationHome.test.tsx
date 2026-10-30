import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import conversationFixture from "../../../fixtures/conversation.json";
import flowFixture from "../../../fixtures/process-flow.json";
import { type ConversationApi, ConversationApiContext, Unreachable } from "../../conversation/api";
import type { Conversation } from "../../conversation/types";
import { type FlowApi, FlowApiContext } from "../../flow/api";
import type { ProcessFlow } from "../../flow/types";
import { type Directory, normalise } from "../../manifest/normalise";
import type { RawAgentsResponse, RawManifestEntry } from "../../manifest/types";
import runFixture from "../../../fixtures/run-succeeded.json";
import { type RunApi, RunApiContext } from "../../run/api";
import type { RunResult } from "../../run/types";
import { ConversationHome } from "./ConversationHome";

const CONVERSATION = conversationFixture as unknown as Conversation;
const FLOW: FlowApi = { get: () => Promise.resolve(flowFixture as ProcessFlow) };
const raw = several as unknown as RawAgentsResponse;
const template: RawManifestEntry | undefined = raw.agents[0];
if (!template) throw new Error("no agent in the fixture");

/** The several-agents set plus an orchestrator, which the profile names. */
function withOrchestrator(assigned: string | null = "advise"): Directory {
  return normalise({
    ...raw,
    profile: { ...raw.profile, orchestrator: "orchestrator.stub" },
    agents: [
      ...raw.agents,
      { ...(template as RawManifestEntry), agent_id: "orchestrator.stub", grounding_mode: "delegation", assigned_action_class: assigned },
    ],
  });
}

function fakeApi(overrides: Partial<ConversationApi> = {}): ConversationApi {
  return {
    create: () => Promise.resolve("c1"),
    sendTurn: () => Promise.resolve(),
    list: () => Promise.resolve([]),
    get: () => Promise.resolve(CONVERSATION),
    ...overrides,
  };
}

function renderHome(directory: Directory, api: ConversationApi, flow: FlowApi = FLOW) {
  return render(
    <FlowApiContext.Provider value={flow}>
      <ConversationApiContext.Provider value={api}>
        <ConversationHome directory={directory} />
      </ConversationApiContext.Provider>
    </FlowApiContext.Provider>,
  );
}

describe("ConversationHome", () => {
  it("says plainly when there is no orchestrator, and links to the directory", async () => {
    renderHome(normalise(raw), fakeApi());
    expect(screen.getByRole("heading", { name: "No conversation is available" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open the agent directory" })).toHaveAttribute(
      "href",
      "/agents",
    );
  });

  it("says when the profile names no orchestrator", () => {
    renderHome(normalise(raw), fakeApi());
    expect(screen.getByText(/names no agent to converse with/)).toBeVisible();
  });

  it("says when the named orchestrator is not available", () => {
    renderHome(normalise({ ...raw, profile: { ...raw.profile, orchestrator: "orchestrator.model" } }), fakeApi());
    expect(screen.getByText(/names orchestrator.model .* not available/)).toBeVisible();
  });

  it("does not converse with a named agent that does not delegate", () => {
    const other = template as RawManifestEntry;
    renderHome(normalise({ ...raw, profile: { ...raw.profile, orchestrator: other.agent_id } }), fakeApi());
    expect(screen.getByText(/does not delegate to other agents/)).toBeVisible();
  });

  it("converses with the named orchestrator, not the first delegation agent", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const delegation = { ...(template as RawManifestEntry), grounding_mode: "delegation" as const, assigned_action_class: "advise" };
    const directory = normalise({
      ...raw,
      profile: { ...raw.profile, orchestrator: "orchestrator.model" },
      agents: [...raw.agents, { ...delegation, agent_id: "orchestrator.stub" }, { ...delegation, agent_id: "orchestrator.model" }],
    });
    renderHome(directory, fakeApi({ sendTurn }));
    await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.model", "hi");
  });

  it("says when the profile does not permit the orchestrator", () => {
    renderHome(withOrchestrator(null), fakeApi());
    expect(screen.getByText(/does not permit orchestrator.stub/)).toBeVisible();
  });

  it("sends a turn, labels replies and children, and returns focus to the message box", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    expect(screen.getByText(/asserted by the operator, not authenticated/)).toBeVisible();
    const box = screen.getByRole("textbox", { name: "What would you like to do?" });
    await userEvent.type(box, "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hello world");
    const transcript = await screen.findByRole("list", { name: "Conversation" });
    expect(within(transcript).getAllByText("orchestrator.stub@0.1.0")).toHaveLength(2);
    expect(within(transcript).getAllByText("example.hello@0.1.0")).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("New reply from orchestrator.stub: Succeeded.");
    expect(box).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sends the message on Ctrl+Enter but not when it is empty", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    const box = screen.getByRole("textbox", { name: "What would you like to do?" });
    await userEvent.type(box, "{Control>}{Enter}{/Control}");
    expect(sendTurn).not.toHaveBeenCalled();
    await userEvent.type(box, "hello");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hello");
  });

  it("marks a version change between turns", async () => {
    const changed: Conversation = {
      ...CONVERSATION,
      version_changes: [{ turn_index: 1, agent_id: "orchestrator.stub", from: "0.1.0", to: "0.2.0" }],
    };
    renderHome(withOrchestrator(), fakeApi({ get: () => Promise.resolve(changed) }));
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/changed version from/)).toBeVisible();
  });

  it("uses the run view's wording for an abstained turn", async () => {
    const [turn] = CONVERSATION.turns;
    if (!turn) throw new Error("no turn");
    const abstained: Conversation = {
      ...CONVERSATION,
      turns: [
        {
          ...turn,
          envelope: {
            ...turn.envelope,
            outcome: { status: "abstained", reason_code: "no_route", statement: "No route." },
          },
        },
      ],
    };
    renderHome(withOrchestrator(), fakeApi({ get: () => Promise.resolve(abstained) }));
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/^Abstained\./)).toBeVisible();
  });

  it("reports a failed send as an alert", async () => {
    renderHome(
      withOrchestrator(),
      fakeApi({ sendTurn: () => Promise.reject(new Error("the server answered 500")) }),
    );
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("the server answered 500");
    // The message returns to the box and the waiting sign goes.
    expect(screen.getByRole("textbox")).toHaveValue("hi");
    expect(screen.queryByText(/is working on a reply/)).not.toBeInTheDocument();
  });

  it("says the server could not be reached, keeps the text and reloads what was stored", async () => {
    const get = vi.fn().mockResolvedValue(conversationFixture as Conversation);
    renderHome(
      withOrchestrator(),
      fakeApi({ sendTurn: () => Promise.reject(new Unreachable()), get }),
    );
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not reach the server, so this message may not have been sent",
    );
    expect(screen.getByRole("textbox")).toHaveValue("hi");
    expect(get).toHaveBeenCalledWith("c1");
  });

  it("shows the message and that the orchestrator is working until the reply arrives", async () => {
    let reply: () => void = () => undefined;
    const sendTurn = () => new Promise<void>((resolve) => (reply = resolve));
    renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    await userEvent.type(screen.getByRole("textbox"), "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    const transcript = await screen.findByRole("list", { name: "Conversation" });
    expect(within(transcript).getByText("hello world")).toBeVisible();
    expect(within(transcript).getByText(/is working on a reply/)).toBeVisible();
    expect(screen.getByRole("textbox")).toHaveValue("");

    reply();
    await screen.findByText("New reply from orchestrator.stub: Succeeded.");
    expect(screen.queryByText(/is working on a reply/)).not.toBeInTheDocument();
  });

  it("reopens a past conversation and starts a new one", async () => {
    const list = () =>
      Promise.resolve([
        { conversation_id: "c9", agent_id: "orchestrator.stub", turns: 2, started_at: "2026-01-01" },
      ]);
    renderHome(withOrchestrator(), fakeApi({ list }));
    await userEvent.click(await screen.findByRole("button", { name: /2026-01-01 \(2 turns\)/ }));
    expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();
  });

  describe("the workspace around the conversation", () => {
    it("lists the Blueprint's six phases and the agents serving each step", async () => {
      const { container } = renderHome(withOrchestrator(), fakeApi());
      const phases = await screen.findByRole("navigation", { name: "Blueprint phases" });
      const items = within(phases).getAllByRole("listitem").filter((li) => li.querySelector("summary"));
      expect(items).toHaveLength(6);
      expect(within(phases).getByText("Pre-collection setup")).toBeVisible();
      await userEvent.click(within(phases).getByText("Pre-collection setup"));
      const step = within(phases).getByText("Select controlled vocabularies and ontologies").closest("li");
      if (!step) throw new Error("no step");
      expect(within(step).getByText(/Requirements: R3/)).toBeVisible();
      expect(within(step).getByRole("link", { name: "Standards Librarian" })).toHaveAttribute(
        "href",
        "/agents?agent=advisor.standards",
      );
      const unserved = within(phases)
        .getByText("Draft the data documentation")
        .closest("li");
      if (!unserved) throw new Error("no step");
      expect(within(unserved).getByText(/No agent here serves this step/)).toBeVisible();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("draws what has no source yet as not built, linked to its issue", () => {
      renderHome(withOrchestrator(), fakeApi());
      const status = screen.getByRole("region", { name: "Where this work stands" });
      for (const label of ["Dataset", "Phase", "Repository", "Governance"]) {
        const dd = within(status).getByText(label).nextElementSibling as HTMLElement;
        expect(within(dd).getByText("Not built yet")).toBeVisible();
        expect(within(dd).getAllByRole("link").length).toBeGreaterThan(0);
      }
      expect(screen.getByRole("heading", { name: "Activity log" })).toBeVisible();
    });

    it("draws the project's documents as not built, and shows whom you are talking to", () => {
      renderHome(withOrchestrator(), fakeApi());
      const panel = screen.getByRole("region", { name: "Project documents" });
      expect(within(panel).getByText("Not built yet")).toBeVisible();
      expect(within(panel).getByRole("link", { name: "#160" })).toBeVisible();
      expect(within(panel).getByText("orchestrator.stub@0.1.0")).toBeVisible();
      expect(within(panel).getByText("Not declared")).toBeVisible();
      expect(within(panel).getByRole("link", { name: "Its full capabilities and limits" })).toHaveAttribute(
        "href",
        "/agents?agent=orchestrator.stub",
      );
    });

    it("keeps the conversation working when the phases cannot be loaded", async () => {
      const failing: FlowApi = { get: () => Promise.reject(new Error("the server answered 500")) };
      renderHome(withOrchestrator(), fakeApi(), failing);
      const phases = screen.getByRole("navigation", { name: "Blueprint phases" });
      expect(await within(phases).findByRole("alert")).toHaveTextContent("the server answered 500");
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toBeEnabled();
    });

    it("keeps the phases and the bar when there is no conversation", async () => {
      renderHome(normalise(raw), fakeApi());
      expect(screen.getByRole("heading", { level: 1, name: "No conversation is available" })).toBeVisible();
      expect(await screen.findByText("Pre-collection setup")).toBeVisible();
      expect(screen.getByRole("region", { name: "Where this work stands" })).toBeVisible();
    });
  });

  describe("the selected run in its card", () => {
    const run = { ...(runFixture as unknown as RunResult) };
    const runs = { get: vi.fn().mockResolvedValue(run) } as unknown as RunApi;

    function renderWithRuns(conversation: Conversation) {
      const api = fakeApi({ get: () => Promise.resolve(conversation) });
      return render(
        <FlowApiContext.Provider value={FLOW}>
          <RunApiContext.Provider value={runs}>
            <ConversationApiContext.Provider value={api}>
              <ConversationHome directory={withOrchestrator()} />
            </ConversationApiContext.Provider>
          </RunApiContext.Provider>
        </FlowApiContext.Provider>,
      );
    }

    async function sendAndSelect(conversation: Conversation) {
      history.replaceState(null, "", "/");
      const view = renderWithRuns(conversation);
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const show = (await screen.findAllByRole("button", { name: /Show the run/ }))[0] as HTMLElement;
      await userEvent.click(show);
      return { ...view, show };
    }

    it("opens the run and its evidence inside the card, keeping the transcript", async () => {
      const { container, show } = await sendAndSelect(CONVERSATION);
      expect(location.search).toMatch(/^\?run=/);
      expect(show).toHaveFocus();
      expect(show).toHaveAttribute("aria-expanded", "true");
      expect(show).toHaveAccessibleName(/^Hide the run/);
      const card = show.closest("li") as HTMLElement;
      expect(card).toHaveAttribute("aria-current", "true");
      expect(await within(card).findByRole("heading", { name: /^Outcome:/ })).toBeVisible();
      expect(within(card).getByRole("heading", { name: /^Evidence/ })).toBeVisible();
      expect(screen.getByRole("list", { name: "Conversation" })).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
      await userEvent.click(show);
      expect(location.search).toBe("");
      expect(show).toHaveAttribute("aria-expanded", "false");
      expect(within(card).queryByRole("heading", { name: /^Outcome:/ })).toBeNull();
    });

    it("opens a linked run that is not in the transcript, as after a reload", async () => {
      history.replaceState(null, "", `/?run=${run.envelope.invocation_id}`);
      renderWithRuns(CONVERSATION);
      const linked = screen.getByRole("region", { name: /^Run / });
      expect(await within(linked).findByRole("heading", { name: /^Outcome:/ })).toBeVisible();
      await userEvent.click(within(linked).getByRole("button", { name: "Close the run" }));
      expect(location.search).toBe("");
      expect(screen.queryByRole("region", { name: /^Run / })).toBeNull();
    });

    it("says a suspended child is waiting for review", async () => {
      const suspended = structuredClone(CONVERSATION);
      for (const t of suspended.turns)
        for (const c of t.children) c.outcome.status = "suspended";
      await sendAndSelect(suspended);
      expect((await screen.findAllByText(/Waiting for review/))[0]).toBeVisible();
    });
  });
});
