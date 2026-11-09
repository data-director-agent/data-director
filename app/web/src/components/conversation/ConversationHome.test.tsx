import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import conversationFixture from "../../../fixtures/conversation.json";
import answeredFixture from "../../../fixtures/conversation-answered.json";
import questionFixture from "../../../fixtures/conversation-question.json";
import leftOut from "../../../fixtures/inventory-left-out.json";
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
import projectsFixture from "../../../fixtures/projects.json";
import projectFixture from "../../../fixtures/project-documents.json";
import {
  type DocumentVersion,
  httpProjectApi,
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocument,
  type ProjectDocuments,
  type ProjectSummary,
} from "../../project/api";
import type { ProcessFlow, ProjectProgress } from "../../flow/types";
import { type Directory, normalise } from "../../manifest/normalise";
import type { RawAgentsResponse, RawManifestEntry } from "../../manifest/types";
import runFixture from "../../../fixtures/run-succeeded.json";
import { type RunApi, RunApiContext, RunRefused } from "../../run/api";
import type { Problem, RunResult } from "../../run/types";
import { ConversationHome } from "./ConversationHome";

const CONVERSATION = conversationFixture as unknown as Conversation;
const PROJECT = projectFixture as ProjectDocuments;
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
    create: () => Promise.resolve({ conversation_id: "c1", project_id: CONVERSATION.project_id ?? null }),
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

const QUESTION = questionFixture as unknown as Conversation;
const ANSWERED = answeredFixture as unknown as Conversation;
const COLLECTED = "Data already collected, being prepared for sharing";

describe("ConversationHome", () => {
  beforeEach(() => {
    localStorage.clear();
    // A conversation is now named in the address, which would carry into the next test.
    history.replaceState(null, "", "/");
  });
  describe("a choice question", () => {
    it("is announced, answered by choosing, and sent beside the labels chosen", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const get = vi.fn().mockResolvedValueOnce(QUESTION).mockResolvedValue(ANSWERED);
      const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn, get }));
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      const group = await screen.findByRole("group", { name: "Where are you with your research data?" });
      expect(screen.getByRole("status")).toHaveTextContent(
        "It asks you to choose: Where are you with your research data?",
      );
      expect(await axe(container)).toHaveNoViolations();
      const send = screen.getByRole("button", { name: "Send answer" });
      expect(send).toBeDisabled();
      await userEvent.click(within(group).getByRole("radio", { name: COLLECTED }));
      await userEvent.click(send);

      const asked = QUESTION.turns[0]?.invocation_id;
      expect(sendTurn).toHaveBeenLastCalledWith("c1", "orchestrator.stub", COLLECTED, asked, null, undefined, {
        answer_to: asked,
        answer_values: ["2"],
      });
      // Answered, the question is read-only with the choice marked in words, and the reply leads
      // on with a question of its own: what to do next (docs/specs/orchestration.md).
      expect(await screen.findByText("(your choice)")).toBeVisible();
      expect(await screen.findByRole("group", { name: "What would you like to do next?" })).toBeVisible();
      expect(screen.getAllByRole("button", { name: "Send answer" })).toHaveLength(1);
    });

    it("keeps the choice, and leaves the message box alone, when the answer is refused", async () => {
      const refused = new RunRefused({ type: "about:blank", title: "Refused", status: 400, detail: "not an option" } as Problem);
      const sendTurn = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(refused);
      renderHome(withOrchestrator(), fakeApi({ sendTurn, get: () => Promise.resolve(QUESTION) }));
      const box = screen.getByRole("textbox", { name: "What would you like to do?" });
      await userEvent.type(box, "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await userEvent.click(await screen.findByRole("radio", { name: COLLECTED }));
      await userEvent.click(screen.getByRole("button", { name: "Send answer" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Refused: not an option");
      expect(screen.getByRole("radio", { name: COLLECTED })).toBeChecked();
      expect(box).toHaveValue("");
    });

    it("may be ignored: a typed message is sent with no answer", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      renderHome(withOrchestrator(), fakeApi({ sendTurn, get: () => Promise.resolve(QUESTION) }));
      const box = screen.getByRole("textbox", { name: "What would you like to do?" });
      await userEvent.type(box, "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await screen.findByRole("group", { name: "Where are you with your research data?" });
      await userEvent.type(box, "ready to deposit");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenLastCalledWith(
        "c1",
        "orchestrator.stub",
        "ready to deposit",
        QUESTION.turns[0]?.invocation_id,
        null,
      );
    });
  });

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
    expect(screen.getByRole("status")).toHaveTextContent(/orchestrator\.stub.*Succeeded/);
    expect(box).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("tells people that Ctrl+Enter sends, as the message box's description", () => {
    renderHome(withOrchestrator(), fakeApi());
    const box = screen.getByRole("textbox", { name: "What would you like to do?" });
    expect(box).toHaveAccessibleDescription(/Ctrl\+Enter.*to send/);
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
    /** Confirms the inventory being checked, leaving nothing out. */
    async function confirm() {
      const review = await screen.findByRole("dialog", { name: "Check the inventory before attaching it" });
      await userEvent.click(within(review).getByRole("button", { name: "Attach this inventory" }));
    }

    it("shows a chosen file as a chip and sends it beside the message", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      await confirm();
      expect(await screen.findByText(/Inventory: 2 files, made 1 Nov 2026/)).toBeVisible();
      expect(screen.queryByRole("button", { name: "Attach inventory" })).toBeNull();
      expect(await axe(container)).toHaveNoViolations();

      // An inventory may be sent with no words.
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "", null, INVENTORY);
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveValue("");
      expect(await screen.findByRole("button", { name: "Attach inventory" })).toBeVisible();
    });

    it("says how to make an inventory, and attaches the file chosen at the end", async () => {
      renderHome(withOrchestrator(), fakeApi());
      await userEvent.click(screen.getByRole("button", { name: "Make an inventory" }));
      const dialog = await screen.findByRole("dialog", { name: "Make an inventory" });
      expect(within(dialog).getAllByText(/uvx data-director-inventory/).length).toBeGreaterThan(0);
      const input = dialog.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input in the dialog");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      await confirm();
      expect(await screen.findByText(/Inventory: 2 files, made 1 Nov 2026/)).toBeVisible();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.queryByRole("button", { name: "Make an inventory" })).toBeNull();
      await waitFor(() =>
        expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveFocus(),
      );
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
      await confirm();
      expect(await screen.findByText(/Inventory: 2 files/)).toBeVisible();
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
      await confirm();
      await userEvent.type(box, "describe these");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(await screen.findByText(/could not reach the server/)).toBeVisible();
      expect(box).toHaveValue("describe these");
      expect(screen.getByRole("button", { name: "Remove inventory" })).toBeVisible();
    });

    it("attaches nothing until the inventory is checked, and nothing when it is cancelled", async () => {
      const { container } = renderHome(withOrchestrator(), fakeApi());
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      const review = await screen.findByRole("dialog", { name: "Check the inventory before attaching it" });
      expect(within(review).getByText(/names of your files and folders/)).toBeVisible();
      expect(within(review).getByText(/AI model hosted outside your institution/)).toBeVisible();
      expect(screen.queryByText(/Inventory: 2 files/)).toBeNull();
      await userEvent.click(within(review).getByRole("button", { name: "Cancel" }));
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.queryByText(/Inventory: 2 files/)).toBeNull();
      expect(screen.getByRole("button", { name: "Attach inventory" })).toBeVisible();
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      await waitFor(() =>
        expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveFocus(),
      );
    });

    it("sends the inventory without the folder and column left out, naming neither", async () => {
      // `app/tests/test_app.py` checks that the project keeps nothing of what is left out of `sent`.
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(leftOut.attached)));
      const review = await screen.findByRole("dialog", { name: "Check the inventory before attaching it" });
      await userEvent.click(within(review).getByRole("checkbox", { name: "Include the folder participants/" }));
      await userEvent.click(within(review).getByText("readings.csv", { selector: "summary *" }));
      await userEvent.click(
        within(review).getByRole("checkbox", { name: "Include the column hiv_status of readings.csv" }),
      );
      expect(within(review).getByRole("status")).toHaveTextContent("Left out: 1 file and 1 column.");
      await userEvent.click(within(review).getByRole("button", { name: "Attach this inventory" }));
      expect(await screen.findByText(/Inventory: 1 file/)).toBeVisible();

      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const sent: unknown = sendTurn.mock.calls[0]?.[4];
      expect(sent).toEqual(leftOut.sent);
      const text = JSON.stringify(sent);
      for (const name of leftOut.left_out) expect(text).not.toContain(name);
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
    expect(await screen.findByText(/orchestrator\.stub.*Succeeded/)).toBeInTheDocument();
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
    await screen.findByText(/orchestrator\.stub.*Succeeded/);
    expect(screen.queryByText(/is working on a reply/)).not.toBeInTheDocument();
  });

  it("reopens a past conversation and starts a new one", async () => {
    const projectId = CONVERSATION.project_id ?? "p1";
    localStorage.setItem("dd-project", projectId);
    const list = () =>
      Promise.resolve([
        {
          conversation_id: "c9",
          agent_id: "orchestrator.stub",
          title: "Depositing a soil survey",
          title_source: "model" as const,
          turns: 2,
          started_at: "2026-01-01T09:30:00Z",
          project_id: projectId,
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

  describe("keeps the open conversation in the address", () => {
    afterEach(() => history.replaceState(null, "", "/"));

    it("reopens the conversation named in the address, as after a reload, and continues it", async () => {
      history.replaceState(null, "", "/?conversation=c9");
      const create = vi.fn(fakeApi().create);
      const sendTurn = vi.fn(() => Promise.resolve());
      renderHome(withOrchestrator(), fakeApi({ create, sendTurn }));
      expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "more");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await waitFor(() => expect(sendTurn).toHaveBeenCalled());
      expect(create).not.toHaveBeenCalled();
      expect((sendTurn.mock.calls[0] as unknown[])[0]).toBe("c9");
    });

    it("names a reopened conversation in the address and clears it for a new one", async () => {
      const projectId = CONVERSATION.project_id ?? "p1";
      localStorage.setItem("dd-project", projectId);
      const list = () =>
        Promise.resolve([
          {
            conversation_id: "c9",
            agent_id: "orchestrator.stub",
            title: "Depositing a soil survey",
            title_source: "model" as const,
            turns: 2,
            started_at: "2026-01-01T09:30:00Z",
            project_id: projectId,
          },
        ]);
      renderHome(withOrchestrator(), fakeApi({ list }));
      await userEvent.click(await screen.findByRole("button", { name: /^Depositing a soil survey / }));
      await screen.findByRole("list", { name: "Conversation" });
      expect(location.search).toBe("?conversation=c9");
      await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
      expect(location.search).toBe("");
    });

    it("says so, and clears the address, when the conversation cannot be opened", async () => {
      history.replaceState(null, "", "/?conversation=gone");
      const get = () => Promise.reject(new Error("not found"));
      renderHome(withOrchestrator(), fakeApi({ get }));
      expect(await screen.findByText(/could not open that conversation/)).toBeVisible();
      expect(location.search).toBe("");
    });
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

    it("links from the conversation to the active project's details", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      renderHome(withOrchestrator(), fakeApi({ list }), FLOW, withProjects);
      const link = await screen.findByRole("link", { name: "Project details" });
      expect(link).toHaveAttribute("href", `/projects/${LOGGERS.project_id}`);
    });

    it("offers no project details link while no project is active", async () => {
      renderHome(withOrchestrator(), fakeApi(), FLOW, {
        ...httpProjectApi,
        projects: () => Promise.resolve([]),
      });
      expect(await screen.findByRole("button", { name: /New project/ })).toBeVisible();
      expect(screen.queryByRole("link", { name: "Project details" })).toBeNull();
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
      const [first] = flowFixture.phases;
      const step = first?.steps[0];
      if (!first || !step) throw new Error("the process-flow fixture has no phase with a step");
      expect(within(bar).getAllByRole("listitem")).toHaveLength(flowFixture.phases.length);
      expect(within(bar).getByText(first.name)).toBeVisible();
      await userEvent.click(within(phases).getByText("Show what happens in each phase"));
      const items = within(phases).getAllByRole("listitem").filter((li) => li.querySelector("summary"));
      expect(items).toHaveLength(flowFixture.phases.length);
      const detail = items.find((li) => li.querySelector("summary")?.textContent?.includes(first.name));
      if (!detail) throw new Error("no phase");
      await userEvent.click(within(detail).getByText(first.name));
      expect(within(detail).getByText(step.label)).toBeVisible();
      expect(phases).not.toHaveTextContent(/Requirements|\bR\d|Served by|agent/);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("shows the Data Management Plan steps and says they are out of scope for now", async () => {
      renderHome(withOrchestrator(), fakeApi());
      const phases = await screen.findByRole("navigation", { name: "Your data journey" });
      await within(phases).findByRole("list", { name: "The phases in order" });
      await userEvent.click(within(phases).getByText("Show what happens in each phase"));
      const detail = within(phases)
        .getAllByRole("listitem")
        .find((li) => li.querySelector("summary")?.textContent?.includes("Plan ahead"));
      if (!detail) throw new Error("no phase");
      await userEvent.click(within(detail).getByText("Plan ahead"));
      const create = within(detail).getByText("Write a Data Management Plan").closest("li");
      expect(create).toHaveTextContent("(optional)");
      expect(create).toHaveTextContent("(out of scope for now)");
      expect(within(detail).getByText("Review your Data Management Plan").closest("li")).toHaveTextContent(
        "(out of scope for now)",
      );
    });

    it("draws what is not built of the project's state, linked to its issues", () => {
      renderHome(withOrchestrator(), fakeApi());
      const state = screen.getByRole("region", { name: "Current state" });
      const repository = within(state).getByText("Repository").nextElementSibling as HTMLElement;
      expect(repository).toHaveTextContent(/None chosen yet/);
      for (const label of ["Dataset", "Phase", "Governance"]) {
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
      const documents = vi.fn<ProjectApi["documents"]>(() =>
        Promise.resolve({ ...PROJECT, project_id: CONVERSATION.project_id ?? "", documents: [] }),
      );
      renderHome(withOrchestrator(), fakeApi({ get, create }), FLOW, { ...httpProjectApi, inventory, documents });
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const panel = screen.getByRole("region", { name: "Project" });
      expect(await within(panel).findByText(/No inventory of the dataset/)).toBeVisible();
      expect(await within(panel).findByText(/No documents drafted yet/)).toBeVisible();
      expect(within(panel).queryByRole("link", { name: "All documents in this project" })).toBeNull();
      expect(documents).toHaveBeenCalledWith(CONVERSATION.project_id, expect.any(AbortSignal));
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "again");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(await within(panel).findByText("Inventory: 42 files, made 1 Nov 2026")).toBeVisible();

      // The whole inventory opens from the chip, fetched from the project.
      await userEvent.click(within(panel).getByRole("button", { name: "View inventory" }));
      const dialog = await screen.findByRole("dialog", { name: "What the inventory holds" });
      expect(await within(dialog).findByText("The inventory lists no files.")).toBeVisible();
      expect(inventory).toHaveBeenCalledWith(CONVERSATION.project_id, expect.any(AbortSignal));
    });

    it("shows a drafted document on its turn and in the side bar, and says it was drafted", async () => {
      const readme = PROJECT.documents[0] as ProjectDocument;
      const draft = readme.versions[0] as DocumentVersion;
      const child = CONVERSATION.turns[CONVERSATION.turns.length - 1]?.children[0];
      if (!child || !draft.drafted_by) throw new Error("the fixtures have no drafter to match");
      const drafted: ProjectDocuments = {
        ...PROJECT,
        project_id: CONVERSATION.project_id ?? "",
        documents: [
          { ...readme, versions: [{ ...draft, drafted_by: { ...draft.drafted_by, invocation_id: child.invocation_id } }] },
          ...PROJECT.documents.slice(1),
        ],
      };
      const documents = vi.fn<ProjectApi["documents"]>(() => Promise.resolve(drafted));
      const { container } = renderHome(withOrchestrator(), fakeApi(), FLOW, { ...httpProjectApi, documents });
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      // The fixture's data dictionary was drafted by the first turn's delegated run, the README by
      // the last turn's: each is a card on its own turn.
      const cards = await screen.findAllByRole("list", { name: "Documents drafted on this turn" });
      expect(cards.map((card) => card.textContent)).toEqual([
        expect.stringContaining("Data dictionary, version 1"),
        expect.stringContaining("README, version 1"),
      ]);
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent(
          "New reply from orchestrator.stub: Succeeded. README drafted, version 1: Proposed, not reviewed.",
        ),
      );

      const panel = screen.getByRole("region", { name: "Project" });
      expect(within(panel).getByRole("heading", { name: "Documents · 1 to review" })).toBeVisible();
      const list = within(panel).getByRole("list", { name: /^Documents/ });
      const rows = within(list).getAllByRole("listitem");
      expect(rows.map((row) => row.textContent)).toEqual([
        "README version 1 Proposed, not reviewed",
        "Data dictionary version 1 Approved",
      ]);
      expect(within(list).getByRole("link", { name: "README" })).toHaveAttribute(
        "href",
        `/projects/${drafted.project_id}?doc=${readme.document_id}`,
      );
      expect(within(panel).getByRole("link", { name: "All documents in this project" })).toHaveAttribute(
        "href",
        `/projects/${drafted.project_id}`,
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("says in the side bar when the project's documents cannot be read", async () => {
      const documents = () => Promise.reject(new Error("the server answered 500"));
      renderHome(withOrchestrator(), fakeApi(), FLOW, { ...httpProjectApi, documents });
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const panel = screen.getByRole("region", { name: "Project" });
      expect(
        await within(panel).findByText(/could not read the project's documents: the server answered 500/),
      ).toBeVisible();
      expect(screen.queryByRole("list", { name: "Documents drafted on this turn" })).toBeNull();
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
            <ActiveProjectProvider>
              <ConversationApiContext.Provider value={api}>
                <ConversationHome directory={withOrchestrator()} />
              </ConversationApiContext.Provider>
            </ActiveProjectProvider>
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
      expect(location.search).toMatch(/^\?conversation=c1&run=/);
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
      expect(location.search).toBe("?conversation=c1");
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

  describe("where the project is in the journey", () => {
    const LOGGERS = (projectsFixture as ProjectSummary[])[0] as ProjectSummary;
    const flow = flowFixture as ProcessFlow;
    const label = (id: string) => {
      const found = flow.phases.flatMap((p) => p.steps).find((s) => s.id === id);
      if (!found) throw new Error(`no step ${id} in the fixture`);
      return found.label;
    };
    const AT_ENTRY_TWO: ProjectProgress = {
      entry: 2,
      steps: { "preparation.files": "done" },
      suggested: "governance.policies",
    };

    function withProgress(overrides: Partial<ProjectApi> = {}): ProjectApi {
      return {
        ...httpProjectApi,
        projects: () => Promise.resolve([LOGGERS]),
        documents: () => Promise.resolve(PROJECT),
        progress: () => Promise.resolve(AT_ENTRY_TWO),
        ...overrides,
      };
    }

    it("shows the harness's suggestion and each step's state, without computing either", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const { container } = renderHome(withOrchestrator(), fakeApi(), FLOW, withProgress());
      const phases = await screen.findByRole("navigation", { name: "Your data journey" });
      expect(await within(phases).findByRole("status")).toHaveTextContent(
        `Suggested next: ${label("governance.policies")}`,
      );
      expect(within(phases).getByRole("combobox", { name: "Where you started" })).toHaveValue("2");
      await userEvent.click(within(phases).getByText("Show what happens in each phase"));
      expect(
        within(phases).getByRole("button", { name: `Open again: ${label("preparation.files")}` }),
      ).toBeInTheDocument();
      expect(phases).not.toHaveTextContent(/\bR\d|agent/);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("records a step marked, or the entry point chosen, and draws what the server reads back", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const markStep = vi.fn(() =>
        Promise.resolve<ProjectProgress>({
          entry: 2,
          steps: { "preparation.files": "done", "governance.policies": "skipped" },
          suggested: "governance.sensitive-data-identify",
        }),
      );
      const chooseEntry = vi.fn(() => Promise.resolve<ProjectProgress>({ ...AT_ENTRY_TWO, entry: 3 }));
      renderHome(withOrchestrator(), fakeApi(), FLOW, withProgress({ markStep, chooseEntry }));
      const phases = await screen.findByRole("navigation", { name: "Your data journey" });
      await within(phases).findByRole("status");
      await userEvent.click(within(phases).getByText("Show what happens in each phase"));
      await userEvent.click(
        within(phases).getByRole("button", { name: `Skip: ${label("governance.policies")}` }),
      );
      expect(markStep).toHaveBeenCalledWith(LOGGERS.project_id, "governance.policies", "skipped");
      expect(await within(phases).findByRole("status")).toHaveTextContent(
        label("governance.sensitive-data-identify"),
      );

      await userEvent.selectOptions(
        within(phases).getByRole("combobox", { name: "Where you started" }),
        "3",
      );
      expect(chooseEntry).toHaveBeenCalledWith(LOGGERS.project_id, 3);
    });
  });
});
