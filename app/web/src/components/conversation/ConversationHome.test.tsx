import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import conversationFixture from "../../../fixtures/conversation.json";
import flowFixture from "../../../fixtures/process-flow.json";
import {
  type ConversationApi,
  ConversationApiContext,
  TurnConflict,
  Unreachable,
} from "../../conversation/api";
import type { Conversation } from "../../conversation/types";
import { type FlowApi, FlowApiContext } from "../../flow/api";
import { ActiveProjectProvider } from "../../project/active";
import {
  httpProjectApi,
  type ProjectApi,
  ProjectApiContext,
  type ProjectSummary,
} from "../../project/api";
import projectsFixture from "../../../fixtures/projects.json";
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
    create: () => Promise.resolve({ conversation_id: "c1", project_id: null }),
    sendTurn: () => Promise.resolve(),
    list: () => Promise.resolve([]),
    get: () => Promise.resolve(CONVERSATION),
    ...overrides,
  };
}

function renderHome(
  directory: Directory,
  api: ConversationApi,
  flow: FlowApi = FLOW,
  project: ProjectApi = httpProjectApi,
) {
  return render(
    <FlowApiContext.Provider value={flow}>
      <ProjectApiContext.Provider value={project}>
        <ActiveProjectProvider>
          <ConversationApiContext.Provider value={api}>
            <ConversationHome directory={directory} />
          </ConversationApiContext.Provider>
        </ActiveProjectProvider>
      </ProjectApiContext.Provider>
    </FlowApiContext.Provider>,
  );
}

describe("ConversationHome", () => {
  beforeEach(() => localStorage.clear());

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
    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.model", "hi", null, null);
  });

  it("says when the profile does not permit the orchestrator", () => {
    renderHome(withOrchestrator(null), fakeApi());
    expect(screen.getByText(/does not permit orchestrator.stub/)).toBeVisible();
  });

  it("sends a turn, labels replies and children, and returns focus to the message box", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    const box = screen.getByRole("textbox", { name: "What would you like to do?" });
    await userEvent.type(box, "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hello world", null, null);
    const transcript = await screen.findByRole("list", { name: "Conversation" });
    expect(within(transcript).getAllByText("orchestrator.stub@0.1.0")).toHaveLength(2);
    expect(within(transcript).getAllByText("example.hello@0.1.1a1")).toHaveLength(2);
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
    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hello", null, null);
  });

  describe("attaching an inventory", () => {
    const INVENTORY = {
      schema_class: "FileInventory",
      inventory_tool: "dd-inventory",
      inventory_tool_version: "0.1.0",
      inventory_made_at: "2026-11-01T09:00:00Z",
      inventory_files: ["a.csv", "b.csv"].map((file_path) => ({
        file_path,
        file_size: 10,
        file_sha256: "0".repeat(64),
        file_identified_by: "extension",
      })),
    };
    const file = (content: string, name = "inventory.json") =>
      new File([content], name, { type: "application/json" });

    it("shows a chosen file as a chip, sends it beside the message, and links to how to make one", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      expect(screen.getByRole("link", { name: "How do I make an inventory?" })).toHaveAttribute(
        "href",
        expect.stringContaining("/user-guide/making-an-inventory/"),
      );
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      expect(await screen.findByText(/Inventory: 2 files, made 1 Nov 2026/)).toBeVisible();
      expect(screen.queryByRole("button", { name: "Attach inventory" })).toBeNull();
      expect(await axe(container)).toHaveNoViolations();

      // An inventory may be sent with no words.
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "", null, INVENTORY);
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveValue("");
      expect(await screen.findByRole("button", { name: "Attach inventory" })).toBeVisible();
    });

    it("says why a file is not an inventory, and attaches nothing", async () => {
      const { container } = renderHome(withOrchestrator(), fakeApi());
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file("not json"));
      expect(await screen.findByRole("alert")).toHaveTextContent("This file is not JSON");
      await userEvent.upload(input, file(JSON.stringify({ schema_class: "Message" })));
      expect(await screen.findByRole("alert")).toHaveTextContent("does not say it is a FileInventory");
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    });

    it("turns a pasted inventory into a chip, not text, and removes it", async () => {
      renderHome(withOrchestrator(), fakeApi());
      const box = screen.getByRole("textbox", { name: "What would you like to do?" });
      await userEvent.click(box);
      await userEvent.paste(JSON.stringify(INVENTORY));
      expect(box).toHaveValue("");
      expect(screen.getByText(/Inventory: 2 files/)).toBeVisible();
      await userEvent.click(screen.getByRole("button", { name: "Remove inventory" }));
      expect(screen.queryByText(/Inventory: 2 files/)).toBeNull();
      expect(box).toHaveFocus();
      // Other text is pasted as it is.
      await userEvent.paste("hello");
      expect(box).toHaveValue("hello");
    });

    it("keeps the inventory attached when the send fails", async () => {
      const sendTurn = vi.fn().mockRejectedValue(new Unreachable());
      renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      const box = screen.getByRole("textbox", { name: "What would you like to do?" });
      await userEvent.click(box);
      await userEvent.paste(JSON.stringify(INVENTORY));
      await userEvent.type(box, "describe these");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(await screen.findByText(/could not reach the server/)).toBeVisible();
      expect(box).toHaveValue("describe these");
      expect(screen.getByRole("button", { name: "Remove inventory" })).toBeVisible();
    });
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

  it("names the latest turn it shows as the one a new turn follows", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText(/New reply from/);
    await userEvent.type(box, "and again");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const latest = CONVERSATION.turns[CONVERSATION.turns.length - 1]?.invocation_id;
    expect(latest).toBeDefined();
    expect(sendTurn).toHaveBeenLastCalledWith("c1", "orchestrator.stub", "and again", latest, null);
  });

  it("says the conversation has moved on, keeps the text and reloads it", async () => {
    const get = vi.fn().mockResolvedValue(CONVERSATION);
    const conflict = new TurnConflict({
      type: "https://example.org/turn-conflict",
      title: "The conversation has moved on",
      http_status: 409,
      detail: "Another turn of this conversation is still running.",
    });
    renderHome(withOrchestrator(), fakeApi({ sendTurn: () => Promise.reject(conflict), get }));
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This conversation has changed since you wrote this",
    );
    expect(screen.getByRole("textbox")).toHaveValue("hi");
    expect(get).toHaveBeenCalledWith("c1");
    expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
  });

  it("reads the reply again when the first read after a turn gets no response", async () => {
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Unreachable())
      .mockResolvedValue(conversationFixture as Conversation);
    renderHome(withOrchestrator(), fakeApi({ get }));
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("New reply from orchestrator.stub: Succeeded.")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not offer a stored turn to be sent again when its reply cannot be shown", async () => {
    renderHome(withOrchestrator(), fakeApi({ get: () => Promise.reject(new Unreachable()) }));
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your message was sent and answered, but Data Director could not show the reply",
    );
    expect(screen.getByRole("textbox")).toHaveValue("");
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
        {
          conversation_id: "c9",
          agent_id: "orchestrator.stub",
          title: "Depositing a soil survey",
          title_source: "model" as const,
          turns: 2,
          started_at: "2026-01-01T09:30:00Z",
        },
      ]);
    renderHome(withOrchestrator(), fakeApi({ list }));
    await userEvent.click(
      await screen.findByRole("button", { name: /^Depositing a soil survey .*, 2 turns$/ }),
    );
    expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
    const history = screen.getByRole("region", { name: "Conversations" });
    expect(within(history).getByRole("button", { name: /^Depositing a soil survey / })).toHaveAttribute(
      "aria-current",
      "true",
    );
    await userEvent.click(within(history).getByRole("button", { name: "New conversation" }));
    expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();
  });

  describe("in one project at a time", () => {
    // The fixture's project is named "My logger data" by its conversation; another is titled.
    const LOGGERS = (projectsFixture as ProjectSummary[])[0] as ProjectSummary;
    const RIVER: ProjectSummary = { ...LOGGERS, project_id: "p2", title: "River loggers" };
    const withProjects: ProjectApi = {
      ...httpProjectApi,
      projects: () => Promise.resolve([LOGGERS, RIVER]),
    };
    const summary = (conversation_id: string, title: string, project_id: string) => ({
      conversation_id,
      project_id,
      agent_id: "orchestrator.stub",
      title,
      title_source: "model" as const,
      turns: 1,
      started_at: "2026-01-01T09:30:00Z",
    });
    const list = () =>
      Promise.resolve([
        summary("c9", "Soil survey", LOGGERS.project_id),
        summary("c8", "River gauges", RIVER.project_id),
      ]);

    it("lists the active project's conversations and starts a new one in it", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const create = vi.fn(() =>
        Promise.resolve({ conversation_id: "c1", project_id: LOGGERS.project_id }),
      );
      renderHome(withOrchestrator(), fakeApi({ list, create }), FLOW, withProjects);
      const history = screen.getByRole("region", { name: "Conversations" });
      expect(await within(history).findByRole("button", { name: /^Soil survey / })).toBeVisible();
      expect(within(history).queryByRole("button", { name: /^River gauges / })).toBeNull();
      expect(await screen.findByRole("button", { name: /My logger data/ })).toBeVisible();

      await userEvent.click(within(history).getByRole("button", { name: "New conversation" }));
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(create).toHaveBeenCalledWith(LOGGERS.project_id);
    });

    it("works in the project a first message starts when none is active", async () => {
      const create = vi.fn(() => Promise.resolve({ conversation_id: "c1", project_id: "p-new" }));
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      renderHome(withOrchestrator(), fakeApi({ create, sendTurn }), FLOW, {
        ...httpProjectApi,
        projects: () => Promise.resolve([]),
      });
      expect(await screen.findByRole("button", { name: /New project/ })).toBeVisible();
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(create).toHaveBeenCalledWith(null);
      expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hi", null, null);
      // The conversation stays open in the project it started.
      expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
      expect(localStorage.getItem("dd-project")).toBe("p-new");
    });

    it("closes the open conversation when another project is chosen", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const get = () => Promise.resolve({ ...CONVERSATION, project_id: LOGGERS.project_id });
      const { container } = renderHome(withOrchestrator(), fakeApi({ list, get }), FLOW, withProjects);
      const history = screen.getByRole("region", { name: "Conversations" });
      await userEvent.click(await within(history).findByRole("button", { name: /^Soil survey / }));
      expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
      expect(await axe(container)).toHaveNoViolations();

      await userEvent.click(screen.getByRole("button", { name: /My logger data/ }));
      await userEvent.click(await screen.findByRole("option", { name: "River loggers" }));
      expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();
      expect(await within(history).findByRole("button", { name: /^River gauges / })).toBeVisible();
      expect(within(history).queryByRole("button", { name: /^Soil survey / })).toBeNull();
      expect(localStorage.getItem("dd-project")).toBe("p2");
    });
  });

  describe("the workspace around the conversation", () => {
    it("lists the six phases of the journey in plain words, with no agents or requirements", async () => {
      const { container } = renderHome(withOrchestrator(), fakeApi());
      const phases = await screen.findByRole("navigation", { name: "Your data journey" });
      const bar = await within(phases).findByRole("list", { name: "The phases in order" });
      expect(within(bar).getAllByRole("listitem")).toHaveLength(6);
      expect(within(bar).getByText("Plan ahead")).toBeVisible();
      await userEvent.click(within(phases).getByText("Show what happens in each phase"));
      const items = within(phases).getAllByRole("listitem").filter((li) => li.querySelector("summary"));
      expect(items).toHaveLength(6);
      const detail = items.find((li) => li.querySelector("summary")?.textContent?.includes("Plan ahead"));
      if (!detail) throw new Error("no phase");
      await userEvent.click(within(detail).getByText("Plan ahead"));
      expect(within(detail).getByText("Choose standard terms to describe your data")).toBeVisible();
      expect(phases).not.toHaveTextContent(/Requirements|\bR\d|Served by|agent/);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("draws the project's current state as not built, linked to its issues", () => {
      renderHome(withOrchestrator(), fakeApi());
      const state = screen.getByRole("region", { name: "Current state" });
      for (const label of ["Dataset", "Phase", "Repository", "Governance"]) {
        const dd = within(state).getByText(label).nextElementSibling as HTMLElement;
        expect(within(dd).getByText("Not built yet")).toBeVisible();
        expect(within(dd).getAllByRole("link").length).toBeGreaterThan(0);
      }
      expect(screen.queryByRole("region", { name: "Where this work stands" })).not.toBeInTheDocument();
      expect(screen.queryByText("Acting for")).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Activity log" })).not.toBeInTheDocument();
    });

    it("says a first message starts a project, and lists no conversations yet", () => {
      renderHome(withOrchestrator(), fakeApi());
      const panel = screen.getByRole("region", { name: "Project" });
      expect(within(panel).getByText(/Your first message starts a new project/)).toBeVisible();
      expect(screen.queryByText("Who you are talking to")).not.toBeInTheDocument();
      const history = screen.getByRole("region", { name: "Conversations" });
      expect(within(history).getByText("No conversations yet.")).toBeVisible();
      expect(within(history).getByRole("button", { name: "New conversation" })).toBeVisible();
    });

    it("links to the conversation's project and says what inventory it holds", async () => {
      const held: Conversation = {
        ...CONVERSATION,
        inventory: { digest: "d", file_count: 42, inventory_made_at: "2026-11-01T09:00:00Z", added_at: "x" },
      };
      const get = vi.fn().mockResolvedValueOnce(CONVERSATION).mockResolvedValue(held);
      const inventory = vi.fn<ProjectApi["inventory"]>(() =>
        Promise.resolve({
          schema_class: "FileInventory",
          inventory_tool: "dd-inventory",
          inventory_tool_version: "0.1.0",
          inventory_made_at: "2026-11-01T09:00:00Z",
          inventory_files: [],
        }),
      );
      const create = () =>
        Promise.resolve({ conversation_id: "c1", project_id: CONVERSATION.project_id ?? null });
      renderHome(withOrchestrator(), fakeApi({ get, create }), FLOW, { ...httpProjectApi, inventory });
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const panel = screen.getByRole("region", { name: "Project" });
      expect(await within(panel).findByText(/No inventory of the dataset/)).toBeVisible();
      expect(within(panel).getByRole("link", { name: "The documents drafted in this project" })).toHaveAttribute(
        "href",
        `/projects/${CONVERSATION.project_id ?? ""}`,
      );
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "again");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(await within(panel).findByText("Inventory: 42 files, made 1 Nov 2026")).toBeVisible();

      // The whole inventory opens from the chip, fetched from the project.
      await userEvent.click(within(panel).getByRole("button", { name: "View inventory" }));
      const dialog = await screen.findByRole("dialog", { name: "What the inventory holds" });
      expect(await within(dialog).findByText("The inventory lists no files.")).toBeVisible();
      expect(inventory).toHaveBeenCalledWith(CONVERSATION.project_id, expect.any(AbortSignal));
    });

    it("keeps the conversation working when the phases cannot be loaded", async () => {
      const failing: FlowApi = { get: () => Promise.reject(new Error("the server answered 500")) };
      renderHome(withOrchestrator(), fakeApi(), failing);
      const phases = screen.getByRole("navigation", { name: "Your data journey" });
      expect(await within(phases).findByRole("alert")).toHaveTextContent("the server answered 500");
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toBeEnabled();
    });

    it("keeps the phases when there is no conversation", async () => {
      renderHome(normalise(raw), fakeApi());
      expect(screen.getByRole("heading", { level: 1, name: "No conversation is available" })).toBeVisible();
      expect((await screen.findAllByText("Plan ahead"))[0]).toBeVisible();
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
