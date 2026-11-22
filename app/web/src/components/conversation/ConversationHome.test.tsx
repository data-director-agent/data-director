import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FileInventory } from "@data-director/inventory";
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
  NoAnswer,
  turnBody,
  Unreachable,
} from "../../conversation/api";
import type { Conversation } from "../../conversation/types";
import { type FlowApi, FlowApiContext } from "../../flow/api";
import { ActiveProjectProvider } from "../../project/active";
import intakeCompleteFixture from "../../../fixtures/intake-complete.json";
import intakePendingFixture from "../../../fixtures/intake-pending.json";
import projectCreatedFixture from "../../../fixtures/project-created.json";
import projectsFixture from "../../../fixtures/projects.json";
import projectFixture from "../../../fixtures/project-documents.json";
import {
  type DocumentVersion,
  httpProjectApi,
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocument,
  type ProjectDocuments,
  type ProjectIntake,
  type ProjectSummary,
} from "../../project/api";
import type { ProcessFlow, ProjectProgress } from "../../flow/types";
import { type Directory, normalise } from "../../manifest/normalise";
import type { RawAgentsResponse, RawManifestEntry } from "../../manifest/types";
import runFixture from "../../../fixtures/run-succeeded.json";
import { conversationSummary, projectProgress, savedInventory } from "../../test/api";
import { type RunApi, RunApiContext, RunRefused } from "../../run/api";
import type { Problem, RunResult } from "../../run/types";
import { cassetteTransport, RunTransportContext, type RunTransport } from "../../run/transport";
import { SUCCEEDED, turnTransport, type TurnSent } from "../../test/turns";
import { AnnouncerProvider } from "../ui/Announcer";
import { ConversationHome } from "./ConversationHome";

/** The frame's polite region, where the page's announcements are said. */
const announcements = () => screen.getByRole("log", { name: "Announcements" });

const CONVERSATION = conversationFixture as unknown as Conversation;
const PROJECT = projectFixture as ProjectDocuments;
const FLOW: FlowApi = {
  get: () => Promise.resolve(flowFixture as ProcessFlow),
};
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
      {
        ...(template as RawManifestEntry),
        agent_id: "orchestrator.stub",
        grounding_mode: "delegation",
        assigned_action_class: assigned,
      },
    ],
  });
}

/** The conversation endpoints, and the turns' stream, whose turns go to `sendTurn`. */
type FakeApi = ConversationApi & { turns: RunTransport };

function fakeApi({
  sendTurn,
  ...overrides
}: Partial<ConversationApi> & { sendTurn?: TurnSent } = {}): FakeApi {
  return {
    create: () =>
      Promise.resolve({
        conversation_id: "c1",
        project_id: CONVERSATION.project_id ?? null,
      }),
    list: () => Promise.resolve([]),
    get: () => Promise.resolve(CONVERSATION),
    remove: () => Promise.reject(new Error("nothing deleted in these tests")),
    restore: () => Promise.resolve(),
    deleted: () => Promise.resolve([]),
    ...overrides,
    turns: turnTransport(sendTurn),
  };
}

/** Renders the page and waits until what it reads on load has landed and it has opened. */
async function renderHome(
  directory: Directory,
  api: FakeApi,
  flow: FlowApi = FLOW,
  project: ProjectApi = httpProjectApi,
) {
  const rendered = render(
    <AnnouncerProvider>
      <FlowApiContext.Provider value={flow}>
        <ProjectApiContext.Provider value={project}>
          <ActiveProjectProvider>
            <ConversationApiContext.Provider value={api}>
              <RunTransportContext.Provider value={api.turns}>
                <ConversationHome directory={directory} />
              </RunTransportContext.Provider>
            </ConversationApiContext.Provider>
          </ActiveProjectProvider>
        </ProjectApiContext.Provider>
      </FlowApiContext.Provider>
    </AnnouncerProvider>,
  );
  return opened(rendered);
}

/** Waits until what the page reads on load has landed and it has opened. */
async function opened<T extends { container: HTMLElement }>(rendered: T): Promise<T> {
  await waitFor(() => expect(rendered.container.querySelector(".page-loading")).toBeNull());
  return rendered;
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
      const get = vi
        .fn()
        .mockResolvedValueOnce(QUESTION)
        .mockResolvedValue(ANSWERED);
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn, get }),
      );
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      const group = await screen.findByRole("group", {
        name: "Where are you with your research data?",
      });
      expect(announcements()).toHaveTextContent(
        "It asks: Where are you with your research data?",
      );
      expect(await axe(container)).toHaveNoViolations();
      const send = screen.getByRole("button", { name: "Send answer" });
      expect(send).toBeDisabled();
      await userEvent.click(
        within(group).getByRole("radio", { name: COLLECTED }),
      );
      await userEvent.click(send);

      const asked = QUESTION.turns[0]?.invocation_id;
      expect(sendTurn).toHaveBeenLastCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          `**Where are you with your research data?**\n\n${COLLECTED}`,
          asked ?? null,
          null,
          {
          answer_to: asked ?? "",
          given_answers: [{ answered_key: "entry", answer_values: ["2"] }],
        },
          null,
        ),
      );
      // Answered, the question is read-only with the choice marked in words, and the reply leads
      // on with a question of its own: what to do next (docs/specs/orchestration.md).
      expect(await screen.findByText("(your choice)")).toBeVisible();
      expect(
        await screen.findByRole("group", {
          name: "What would you like to do next?",
        }),
      ).toBeVisible();
      expect(
        screen.getAllByRole("button", { name: "Send answer" }),
      ).toHaveLength(1);
    });

    it("keeps the choice, and leaves the message box alone, when the answer is refused", async () => {
      const refused = new RunRefused({
        type: "about:blank",
        title: "Refused",
        status: 400,
        detail: "not an option",
      } as Problem);
      const sendTurn = vi
        .fn()
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(refused);
      await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn, get: () => Promise.resolve(QUESTION) }),
      );
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      await userEvent.type(box, "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await userEvent.click(
        await screen.findByRole("radio", { name: COLLECTED }),
      );
      await userEvent.click(
        screen.getByRole("button", { name: "Send answer" }),
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Refused: not an option",
      );
      expect(screen.getByRole("radio", { name: COLLECTED })).toBeChecked();
      await userEvent.click(screen.getByRole("button", { name: "Reply in my own words instead" }));
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveValue("");
    });

    it("may be ignored: a typed message is sent with no answer", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn, get: () => Promise.resolve(QUESTION) }),
      );
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      await userEvent.type(box, "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await screen.findByRole("group", {
        name: "Where are you with your research data?",
      });
      // One way of replying shows at a time: the questions take the message box's place.
      expect(screen.queryByRole("textbox", { name: "What would you like to do?" })).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "Reply in my own words instead" }));
      expect(screen.queryByRole("group", { name: "Where are you with your research data?" })).toBeNull();
      await userEvent.type(
        await screen.findByRole("textbox", { name: "What would you like to do?" }),
        "ready to deposit",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenLastCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          "ready to deposit",
          QUESTION.turns[0]?.invocation_id ?? null,
          null,
          null,
          null,
        ),
      );
    });

    it("swaps back from the message box to the questions, keeping what was chosen", async () => {
      await renderHome(withOrchestrator(), fakeApi({ get: () => Promise.resolve(QUESTION) }));
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await userEvent.click(await screen.findByRole("radio", { name: COLLECTED }));
      await userEvent.click(screen.getByRole("button", { name: "Reply in my own words instead" }));
      await waitFor(() =>
        expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveFocus(),
      );
      await userEvent.click(screen.getByRole("button", { name: "Answer the questions instead" }));
      expect(screen.queryByRole("textbox", { name: "What would you like to do?" })).toBeNull();
      expect(screen.getByRole("radio", { name: COLLECTED })).toBeChecked();
    });

    it("sends a file attached while answering beside the answers", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn, get: () => Promise.resolve(QUESTION) }),
      );
      await userEvent.type(screen.getByRole("textbox", { name: "What would you like to do?" }), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const group = await screen.findByRole("group", { name: "Where are you with your research data?" });
      const form = group.closest("form");
      if (!form) throw new Error("no form");
      expect(within(form).getByRole("button", { name: "Attach a file" })).toBeVisible();
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, new File(["# Plan"], "plan.md", { type: "text/markdown" }));
      const review = await screen.findByRole("dialog", { name: "Check the document before attaching it" });
      await userEvent.click(within(review).getByRole("button", { name: "Attach this document" }));
      expect(await within(form).findByText(/Document: plan.md/)).toBeVisible();
      await userEvent.click(within(group).getByRole("radio", { name: COLLECTED }));
      await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
      expect(sendTurn).toHaveBeenLastCalledWith(
        "c1",
        expect.objectContaining({
          reply_answers: expect.objectContaining({ answer_to: QUESTION.turns[0]?.invocation_id }),
          documentation: expect.objectContaining({ name: "plan.md", text: "# Plan" }),
        }),
      );
    });
  });

  it("says plainly when there is no orchestrator, and links to the directory", async () => {
    await renderHome(normalise(raw), fakeApi());
    expect(
      screen.getByRole("heading", { name: "No conversation is available" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open the agent directory" }),
    ).toHaveAttribute("href", "/agents");
  });

  it("says when the profile names no orchestrator", async () => {
    await renderHome(normalise(raw), fakeApi());
    expect(screen.getByText(/names no agent to converse with/)).toBeVisible();
  });

  it("says when the named orchestrator is not available", async () => {
    await renderHome(
      normalise({
        ...raw,
        profile: { ...raw.profile, orchestrator: "orchestrator.model" },
      }),
      fakeApi(),
    );
    expect(
      screen.getByText(/names orchestrator.model .* not available/),
    ).toBeVisible();
  });

  it("does not converse with a named agent that does not delegate", async () => {
    const other = template as RawManifestEntry;
    await renderHome(
      normalise({
        ...raw,
        profile: { ...raw.profile, orchestrator: other.agent_id },
      }),
      fakeApi(),
    );
    expect(screen.getByText(/does not delegate to other agents/)).toBeVisible();
  });

  it("converses with the named orchestrator, not the first delegation agent", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const delegation = {
      ...(template as RawManifestEntry),
      grounding_mode: "delegation" as const,
      assigned_action_class: "advise",
    };
    const directory = normalise({
      ...raw,
      profile: { ...raw.profile, orchestrator: "orchestrator.model" },
      agents: [
        ...raw.agents,
        { ...delegation, agent_id: "orchestrator.stub" },
        { ...delegation, agent_id: "orchestrator.model" },
      ],
    });
    await renderHome(directory, fakeApi({ sendTurn }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "What would you like to do?" }),
      "hi",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          "orchestrator.model",
          "hi",
          null,
          null,
          null,
          null,
        ),
      );
  });

  it("says when the profile does not permit the orchestrator", async () => {
    await renderHome(withOrchestrator(null), fakeApi());
    expect(screen.getByText(/does not permit orchestrator.stub/)).toBeVisible();
  });

  it("sends a turn, labels replies and children, and returns focus to the message box", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { container } = await renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    const box = screen.getByRole("textbox", {
      name: "What would you like to do?",
    });
    await userEvent.type(box, "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          "hello world",
          null,
          null,
          null,
          null,
        ),
      );
    const transcript = await screen.findByRole("list", {
      name: "Conversation",
    });
    // Each agent is named, never shown by its version or model.
    expect(
      within(transcript).getAllByText("Friendly Greeter"),
    ).toHaveLength(4);
    for (const heading of transcript.querySelectorAll(".turn-speaker")) {
      expect(heading).not.toHaveTextContent("@");
    }
    expect(within(transcript).queryByText(/Language model/)).toBeNull();
    expect(announcements()).toHaveTextContent(
      /orchestrator\.stub.*Succeeded/,
    );
    expect(box).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("tells people that Ctrl+Enter sends, as the message box's description", async () => {
    await renderHome(withOrchestrator(), fakeApi());
    const box = screen.getByRole("textbox", {
      name: "What would you like to do?",
    });
    expect(box).toHaveAccessibleDescription(/Ctrl\+Enter.*to send/);
  });

  it("sends the message on Ctrl+Enter but not when it is empty", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    await renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    const box = screen.getByRole("textbox", {
      name: "What would you like to do?",
    });
    await userEvent.type(box, "{Control>}{Enter}{/Control}");
    expect(sendTurn).not.toHaveBeenCalled();
    await userEvent.type(box, "hello");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          "hello",
          null,
          null,
          null,
          null,
        ),
      );
  });

  describe("attaching a document", () => {
    const PROTOCOL = "# Sampling protocol\n\nSediment cores were taken monthly.\n";
    const doc = (content: string, name = "protocol.md", type = "text/markdown") =>
      new File([content], name, { type });
    function fileInput(container: HTMLElement): HTMLInputElement {
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      return input;
    }
    async function confirmDocument() {
      const review = await screen.findByRole("dialog", { name: "Check the document before attaching it" });
      await userEvent.click(within(review).getByRole("button", { name: "Attach this document" }));
    }

    it("checks a chosen document, shows it as a chip and sends it beside the message", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = await renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      await userEvent.upload(fileInput(container), doc(PROTOCOL));
      const review = await screen.findByRole("dialog", { name: "Check the document before attaching it" });
      expect(within(review).getByText(/Sediment cores were taken monthly/)).toBeVisible();
      expect(within(review).getByText(/never\s+the data themselves/)).toBeVisible();
      expect(await axe(review)).toHaveNoViolations();
      await confirmDocument();
      expect(await screen.findByText(/Document: protocol.md/)).toBeVisible();
      // Its text is never put into the message.
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveValue("");
      expect(await axe(container)).toHaveNoViolations();

      // A document may be sent with no words.
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        expect.objectContaining({
          agent_id: "orchestrator.stub",
          message_text: "",
          follows: null,
          documentation: expect.objectContaining({ name: "protocol.md", media_type: "text/markdown", text: PROTOCOL }),
        }),
      );
      await waitFor(() => expect(screen.queryByText(/Document: protocol.md/)).toBeNull());
    });

    it("attaches nothing when the check is cancelled, and removes an attached document", async () => {
      const { container } = await renderHome(withOrchestrator(), fakeApi());
      await userEvent.upload(fileInput(container), doc("age: years", "codebook.txt", "text/plain"));
      const review = await screen.findByRole("dialog", { name: "Check the document before attaching it" });
      await userEvent.click(within(review).getByRole("button", { name: "Cancel" }));
      expect(screen.queryByText(/Document: codebook.txt/)).toBeNull();
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

      await userEvent.upload(fileInput(container), doc("age: years", "codebook.txt", "text/plain"));
      await confirmDocument();
      expect(await screen.findByText(/Document: codebook.txt/)).toBeVisible();
      await userEvent.click(screen.getByRole("button", { name: "Remove codebook.txt" }));
      expect(screen.queryByText(/Document: codebook.txt/)).toBeNull();
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toHaveFocus();
    });

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
      const review = await screen.findByRole("dialog", {
        name: "Check the inventory before attaching it",
      });
      await userEvent.click(
        within(review).getByRole("button", { name: "Attach this inventory" }),
      );
    }

    it("shows a chosen file as a chip and sends it beside the message", async () => {
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn }),
      );
      const input =
        container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      await confirm();
      expect(
        await screen.findByText(/Inventory: 2 files, made 1 Nov 2026/),
      ).toBeVisible();
      // A document may still be attached beside it.
      expect(
        screen.getByRole("button", { name: "Attach a file" }),
      ).toBeVisible();
      expect(await axe(container)).toHaveNoViolations();

      // An inventory may be sent with no words.
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          "",
          null,
          INVENTORY as FileInventory,
          null,
          null,
        ),
      );
      expect(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
      ).toHaveValue("");
      expect(
        await screen.findByRole("button", { name: "Attach a file" }),
      ).toBeVisible();
    });

    it("offers Attach a file under the message box but not Make an inventory", async () => {
      await renderHome(withOrchestrator(), fakeApi());
      const form = screen
        .getByRole("textbox", { name: "What would you like to do?" })
        .closest("form");
      if (!form) throw new Error("the message box is in no form");
      expect(
        within(form).getByRole("button", { name: "Attach a file" }),
      ).toBeVisible();
      expect(
        within(form).queryByRole("button", { name: "Make an inventory" }),
      ).toBeNull();
    });

    it("says a gateway error may mean the message is still being answered, and reloads", async () => {
      const get = vi.fn().mockResolvedValue(conversationFixture as Conversation);
      await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn: () => Promise.reject(new NoAnswer(502)), get }),
      );
      await userEvent.type(screen.getByRole("textbox"), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "did not answer in time (it answered 502)",
      );
      expect(screen.getByRole("textbox")).toHaveValue("hi");
      expect(get).toHaveBeenCalledWith("c1");
    });

    it("keeps the inventory attached when the send fails", async () => {
      const sendTurn = vi.fn().mockRejectedValue(new Unreachable());
      await renderHome(withOrchestrator(), fakeApi({ sendTurn }));
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      await userEvent.click(box);
      await userEvent.paste(JSON.stringify(INVENTORY));
      await confirm();
      await userEvent.type(box, "describe these");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(
        await screen.findByText(/could not reach the server/),
      ).toBeVisible();
      expect(box).toHaveValue("describe these");
      expect(
        screen.getByRole("button", { name: "Remove inventory" }),
      ).toBeVisible();
    });

    it("attaches nothing until the inventory is checked, and nothing when it is cancelled", async () => {
      const { container } = await renderHome(withOrchestrator(), fakeApi());
      const input =
        container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(INVENTORY)));
      const review = await screen.findByRole("dialog", {
        name: "Check the inventory before attaching it",
      });
      expect(
        within(review).getByText(/names of your files and folders/),
      ).toBeVisible();
      expect(
        within(review).getByText(/AI model hosted outside your institution/),
      ).toBeVisible();
      expect(screen.queryByText(/Inventory: 2 files/)).toBeNull();
      await userEvent.click(
        within(review).getByRole("button", { name: "Cancel" }),
      );
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.queryByText(/Inventory: 2 files/)).toBeNull();
      expect(
        screen.getByRole("button", { name: "Attach a file" }),
      ).toBeVisible();
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      await waitFor(() =>
        expect(
          screen.getByRole("textbox", { name: "What would you like to do?" }),
        ).toHaveFocus(),
      );
    });

    it("sends the inventory without the folder and column left out, naming neither", async () => {
      // `app/tests/test_app.py` checks that the project keeps nothing of what is left out of `sent`.
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn }),
      );
      const input =
        container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("no file input");
      await userEvent.upload(input, file(JSON.stringify(leftOut.attached)));
      const review = await screen.findByRole("dialog", {
        name: "Check the inventory before attaching it",
      });
      await userEvent.click(
        within(review).getByRole("checkbox", {
          name: "Include the folder participants/",
        }),
      );
      await userEvent.click(
        within(review).getByText("readings.csv", { selector: ".inventory-table summary *" }),
      );
      await userEvent.click(
        within(review).getByRole("checkbox", {
          name: "Include the column hiv_status of readings.csv",
        }),
      );
      expect(within(review).getByRole("status")).toHaveTextContent(
        "1 file and 1 column left out",
      );
      await userEvent.click(
        within(review).getByRole("button", { name: "Attach this inventory" }),
      );
      expect(await screen.findByText(/Inventory: 1 file/)).toBeVisible();

      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const body = sendTurn.mock.calls[0]?.[1] as Record<string, unknown>;
      const sent: unknown = body.inventory;
      expect(sent).toEqual(leftOut.sent);
      const text = JSON.stringify(sent);
      for (const name of leftOut.left_out) expect(text).not.toContain(name);
    });
  });

  it("says in plain words that an agent was updated between turns", async () => {
    const changed: Conversation = {
      ...CONVERSATION,
      version_changes: [
        {
          turn_index: 1,
          agent_id: "orchestrator.stub",
          from: "0.1.0",
          to: "0.2.0",
        },
      ],
    };
    await renderHome(
      withOrchestrator(),
      fakeApi({ get: () => Promise.resolve(changed) }),
    );
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const note = await screen.findByText(/was updated since an earlier turn/);
    expect(note).toBeVisible();
    expect(note).not.toHaveTextContent("0.2.0");
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
            outcome: {
              status: "abstained",
              reason_code: "no_route",
              statement: "No route.",
            },
          },
        },
      ],
    };
    await renderHome(
      withOrchestrator(),
      fakeApi({ get: () => Promise.resolve(abstained) }),
    );
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/^Abstained\./)).toBeVisible();
  });

  it("reports a failed send as an alert", async () => {
    await renderHome(
      withOrchestrator(),
      fakeApi({
        sendTurn: () => Promise.reject(new Error("the server answered 500")),
      }),
    );
    await userEvent.type(screen.getByRole("textbox"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the server answered 500",
    );
    // The message returns to the box and the waiting sign goes.
    expect(screen.getByRole("textbox")).toHaveValue("hi");
    expect(screen.queryByText(/is working on a reply/)).not.toBeInTheDocument();
  });

  it("shows the message and that the orchestrator is working until the reply arrives", async () => {
    let reply: () => void = () => undefined;
    const sendTurn = () => new Promise<void>((resolve) => (reply = () => resolve()));
    await renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    await userEvent.type(screen.getByRole("textbox"), "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    const transcript = await screen.findByRole("list", {
      name: "Conversation",
    });
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
        conversationSummary({
          conversation_id: "c9",
          agent_id: "orchestrator.stub",
          title: "Depositing a soil survey",
          turns: 2,
          project_id: projectId,
        }),
      ]);
    await renderHome(withOrchestrator(), fakeApi({ list }));
    await userEvent.click(
      await screen.findByRole("button", {
        name: /^Depositing a soil survey .*, 2 turns$/,
      }),
    );
    expect(
      await screen.findByRole("list", { name: "Conversation" }),
    ).toBeVisible();
    const history = screen.getByRole("region", { name: "Conversations" });
    expect(
      within(history).getByRole("button", {
        name: /^Depositing a soil survey /,
      }),
    ).toHaveAttribute("aria-current", "true");
    await userEvent.click(
      within(history).getByRole("button", { name: "New conversation" }),
    );
    expect(
      screen.queryByRole("list", { name: "Conversation" }),
    ).not.toBeInTheDocument();
  });

  describe("keeps the open conversation in the address", () => {
    afterEach(() => history.replaceState(null, "", "/"));

    it("reopens the conversation named in the address, as after a reload, and continues it", async () => {
      history.replaceState(null, "", "/?conversation=c9");
      const create = vi.fn(fakeApi().create);
      const sendTurn = vi.fn(() => Promise.resolve());
      await renderHome(withOrchestrator(), fakeApi({ create, sendTurn }));
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
          conversationSummary({
            conversation_id: "c9",
            agent_id: "orchestrator.stub",
            title: "Depositing a soil survey",
            turns: 2,
            project_id: projectId,
          }),
        ]);
      await renderHome(withOrchestrator(), fakeApi({ list }));
      await userEvent.click(await screen.findByRole("button", { name: /^Depositing a soil survey / }));
      await screen.findByRole("list", { name: "Conversation" });
      expect(location.search).toBe("?conversation=c9");
      await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
      expect(location.search).toBe("");
    });

    it("says so, and clears the address, when the conversation cannot be opened", async () => {
      history.replaceState(null, "", "/?conversation=gone");
      const get = () => Promise.reject(new Error("not found"));
      await renderHome(withOrchestrator(), fakeApi({ get }));
      expect(await screen.findByText(/could not open that conversation/)).toBeVisible();
      expect(location.search).toBe("");
    });
  });

  describe("in one project at a time", () => {
    // The fixture's project is named "My logger data" by its conversation; another is titled.
    const LOGGERS = (projectsFixture as ProjectSummary[])[0] as ProjectSummary;
    const RIVER: ProjectSummary = {
      ...LOGGERS,
      project_id: "p2",
      title: "River loggers",
    };
    const withProjects: ProjectApi = {
      ...httpProjectApi,
      projects: () => Promise.resolve([LOGGERS, RIVER]),
    };
    const summary = (
      conversation_id: string,
      title: string,
      project_id: string,
    ) => conversationSummary({ conversation_id, project_id, agent_id: "orchestrator.stub", title });
    const list = () =>
      Promise.resolve([
        summary("c9", "Soil survey", LOGGERS.project_id),
        summary("c8", "River gauges", RIVER.project_id),
      ]);

    it("lists the active project's conversations and starts a new one in it", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const create = vi.fn(() =>
        Promise.resolve({
          conversation_id: "c1",
          project_id: LOGGERS.project_id,
        }),
      );
      await renderHome(
        withOrchestrator(),
        fakeApi({ list, create }),
        FLOW,
        withProjects,
      );
      const history = screen.getByRole("region", { name: "Conversations" });
      expect(
        await within(history).findByRole("button", { name: /^Soil survey / }),
      ).toBeVisible();
      expect(
        within(history).queryByRole("button", { name: /^River gauges / }),
      ).toBeNull();
      expect(
        await screen.findByRole("button", { name: /My logger data/ }),
      ).toBeVisible();

      await userEvent.click(
        within(history).getByRole("button", { name: "New conversation" }),
      );
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(create).toHaveBeenCalledWith(LOGGERS.project_id);
    });

    it("works in the project a first message starts when none is active", async () => {
      const create = vi.fn(() =>
        Promise.resolve({ conversation_id: "c1", project_id: "p-new" }),
      );
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      await renderHome(withOrchestrator(), fakeApi({ create, sendTurn }), FLOW, {
        ...httpProjectApi,
        projects: () => Promise.resolve([]),
      });
      expect(
        await screen.findByRole("button", { name: /No project/ }),
      ).toBeVisible();
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(create).toHaveBeenCalledWith(null);
      expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          "orchestrator.stub",
          "hi",
          null,
          null,
          null,
          null,
        ),
      );
      // The conversation stays open in the project it started.
      expect(
        await screen.findByRole("list", { name: "Conversation" }),
      ).toBeVisible();
      expect(localStorage.getItem("dd-project")).toBe("p-new");
    });

    it("links from the conversation to the active project's details", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      await renderHome(withOrchestrator(), fakeApi({ list }), FLOW, withProjects);
      const link = await screen.findByRole("link", { name: "Project details" });
      expect(link).toHaveAttribute("href", `/projects/${LOGGERS.project_id}`);
    });

    it("offers no project details link while no project is active", async () => {
      await renderHome(withOrchestrator(), fakeApi(), FLOW, {
        ...httpProjectApi,
        projects: () => Promise.resolve([]),
      });
      expect(
        await screen.findByRole("button", { name: /No project/ }),
      ).toBeVisible();
      expect(
        screen.queryByRole("link", { name: "Project details" }),
      ).toBeNull();
    });

    it("closes the open conversation when another project is chosen", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const get = () =>
        Promise.resolve({ ...CONVERSATION, project_id: LOGGERS.project_id });
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ list, get }),
        FLOW,
        withProjects,
      );
      const history = screen.getByRole("region", { name: "Conversations" });
      await userEvent.click(
        await within(history).findByRole("button", { name: /^Soil survey / }),
      );
      expect(
        await screen.findByRole("list", { name: "Conversation" }),
      ).toBeVisible();
      expect(await axe(container)).toHaveNoViolations();

      await userEvent.click(
        screen.getByRole("button", { name: /My logger data/ }),
      );
      await userEvent.click(
        await screen.findByRole("option", { name: "River loggers" }),
      );
      expect(
        screen.queryByRole("list", { name: "Conversation" }),
      ).not.toBeInTheDocument();
      // The other project's workspace opens afresh once its reads have landed.
      const other = await screen.findByRole("region", { name: "Conversations" });
      expect(
        await within(other).findByRole("button", { name: /^River gauges / }),
      ).toBeVisible();
      expect(
        within(other).queryByRole("button", { name: /^Soil survey / }),
      ).toBeNull();
      expect(localStorage.getItem("dd-project")).toBe("p2");
    });
  });

  describe("the workspace around the conversation", () => {
    it("lists the six phases of the journey in plain words, with no agents or requirements", async () => {
      const { container } = await renderHome(withOrchestrator(), fakeApi());
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      const bar = await within(phases).findByRole("list", {
        name: "The phases in order",
      });
      const [first] = flowFixture.phases;
      const step = first?.steps[0];
      if (!first || !step)
        throw new Error("the process-flow fixture has no phase with a step");
      expect(within(bar).getAllByRole("listitem")).toHaveLength(
        flowFixture.phases.length,
      );
      expect(within(bar).getByText(first.name)).toBeVisible();
      await userEvent.click(
        within(phases).getByText("Show what happens in each phase"),
      );
      const items = within(phases)
        .getAllByRole("listitem")
        .filter((li) => li.querySelector("summary"));
      expect(items).toHaveLength(flowFixture.phases.length);
      const detail = items.find((li) =>
        li.querySelector("summary")?.textContent?.includes(first.name),
      );
      if (!detail) throw new Error("no phase");
      await userEvent.click(within(detail).getByText(first.name));
      expect(within(detail).getByText(step.label)).toBeVisible();
      expect(phases).not.toHaveTextContent(
        /Requirements|\bR\d|Served by|agent/,
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("shows the Data Management Plan steps and says they are out of scope for now", async () => {
      await renderHome(withOrchestrator(), fakeApi());
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      await within(phases).findByRole("list", { name: "The phases in order" });
      await userEvent.click(
        within(phases).getByText("Show what happens in each phase"),
      );
      const detail = within(phases)
        .getAllByRole("listitem")
        .find((li) =>
          li.querySelector("summary")?.textContent?.includes("Plan ahead"),
        );
      if (!detail) throw new Error("no phase");
      await userEvent.click(within(detail).getByText("Plan ahead"));
      const create = within(detail)
        .getByText("Write a Data Management Plan")
        .closest("li");
      expect(create).toHaveTextContent("(optional)");
      expect(create).toHaveTextContent("(out of scope for now)");
      expect(
        within(detail)
          .getByText("Review your Data Management Plan")
          .closest("li"),
      ).toHaveTextContent("(out of scope for now)");
    });

    it("draws what is not built of the project pane, linked to its issues", async () => {
      await renderHome(withOrchestrator(), fakeApi());
      const panel = screen.getByRole("region", { name: "Project" });
      const guardrails = within(panel).getByRole("region", { name: "Guardrails" });
      expect(
        within(guardrails).getByRole("link", {
          name: "What Data Director may do at each step",
        }),
      ).toHaveAttribute("href", "/policy#policy-steps");
      for (const badge of within(guardrails).getAllByText("Not built yet")) {
        expect(
          within(badge.parentElement as HTMLElement).getAllByRole("link").length,
        ).toBeGreaterThan(0);
      }
      expect(
        screen.queryByRole("region", { name: "Where this work stands" }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Acting for")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: "Activity log" }),
      ).not.toBeInTheDocument();
    });

    it("says a first message starts a project, and lists no conversations yet", async () => {
      await renderHome(withOrchestrator(), fakeApi());
      const panel = screen.getByRole("region", { name: "Project" });
      expect(
        within(panel).getByText(/Your first message starts a new project/),
      ).toBeVisible();
      expect(
        screen.queryByText("Who you are talking to"),
      ).not.toBeInTheDocument();
      const history = screen.getByRole("region", { name: "Conversations" });
      expect(within(history).getByText("No conversations yet.")).toBeVisible();
      expect(
        within(history).getByRole("button", { name: "New conversation" }),
      ).toBeVisible();
    });

    it("links to the conversation's project and says what inventory it holds", async () => {
      const held: Conversation = {
        ...CONVERSATION,
        inventory: savedInventory({
          digest: "d",
          file_count: 42,
          inventory_made_at: "2026-11-01T09:00:00Z",
          added_at: "x",
        }),
      };
      const get = vi
        .fn()
        .mockResolvedValueOnce(CONVERSATION)
        .mockResolvedValue(held);
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
        Promise.resolve({
          conversation_id: "c1",
          project_id: CONVERSATION.project_id ?? null,
        });
      const documents = vi.fn<ProjectApi["documents"]>(() =>
        Promise.resolve({
          ...PROJECT,
          project_id: CONVERSATION.project_id ?? "",
          documents: [],
        }),
      );
      await renderHome(withOrchestrator(), fakeApi({ get, create }), FLOW, {
        ...httpProjectApi,
        inventory,
        documents,
      });
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const panel = screen.getByRole("region", { name: "Project" });
      expect(
        await within(panel).findByText(/No inventory of the dataset/),
      ).toBeVisible();
      expect(
        await within(panel).findByText(/No documents drafted yet/),
      ).toBeVisible();
      expect(
        within(panel).queryByRole("link", {
          name: "All documents in this project",
        }),
      ).toBeNull();
      expect(documents).toHaveBeenCalledWith(
        CONVERSATION.project_id,
        expect.any(AbortSignal),
      );
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "again",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(
        await within(panel).findByText("Inventory: 42 files, made 1 Nov 2026"),
      ).toBeVisible();

      // The whole inventory opens from the chip, fetched from the project.
      await userEvent.click(
        within(panel).getByRole("button", { name: "View inventory" }),
      );
      const dialog = await screen.findByRole("dialog", {
        name: "What the inventory holds",
      });
      expect(
        await within(dialog).findByText("The inventory lists no files."),
      ).toBeVisible();
      expect(inventory).toHaveBeenCalledWith(
        CONVERSATION.project_id,
        expect.any(AbortSignal),
      );
    });

    it("shows a drafted document on its turn and in the side bar, and says it was drafted", async () => {
      const readme = PROJECT.documents[0] as ProjectDocument;
      const draft = readme.versions[0] as DocumentVersion;
      const child =
        CONVERSATION.turns[CONVERSATION.turns.length - 1]?.children[0];
      if (!child || !draft.drafted_by)
        throw new Error("the fixtures have no drafter to match");
      const drafted: ProjectDocuments = {
        ...PROJECT,
        project_id: CONVERSATION.project_id ?? "",
        documents: [
          {
            ...readme,
            versions: [
              {
                ...draft,
                drafted_by: {
                  ...draft.drafted_by,
                  invocation_id: child.invocation_id,
                },
              },
            ],
          },
          ...PROJECT.documents.slice(1),
        ],
      };
      const documents = vi.fn<ProjectApi["documents"]>(() =>
        Promise.resolve(drafted),
      );
      const { container } = await renderHome(withOrchestrator(), fakeApi(), FLOW, {
        ...httpProjectApi,
        documents,
      });
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      // The fixture's data dictionary was drafted by the first turn's delegated run, the README by
      // the last turn's: each is a card on its own turn.
      const cards = await screen.findAllByRole("list", {
        name: "Documents drafted on this turn",
      });
      expect(cards.map((card) => card.textContent)).toEqual([
        expect.stringContaining("Data dictionary, version 1"),
        expect.stringContaining("README, version 1"),
      ]);
      await waitFor(() =>
        expect(announcements()).toHaveTextContent(
          "New reply from orchestrator.stub: Succeeded. README drafted, version 1: Proposed, not reviewed.",
        ),
      );

      const panel = screen.getByRole("region", { name: "Project" });
      // The proposed README waits on the researcher, with a way to its review.
      const waiting = within(panel).getByRole("list", { name: /^Waiting on you/ });
      expect(
        within(waiting).getByRole("link", { name: "Review" }),
      ).toHaveAttribute(
        "href",
        `/projects/${drafted.project_id}?doc=${readme.document_id}`,
      );
      // Both documents were drafted by this conversation's runs, so they are listed as its own.
      const list = within(panel).getByRole("list", { name: "From this conversation" });
      const rows = within(list).getAllByRole("listitem");
      expect(rows).toHaveLength(2);
      expect(
        within(list).getByRole("link", { name: "README" }),
      ).toHaveAttribute(
        "href",
        `/projects/${drafted.project_id}?doc=${readme.document_id}`,
      );
      expect(
        within(panel).getByRole("link", { name: "All documents" }),
      ).toHaveAttribute("href", `/projects/${drafted.project_id}`);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("says in the side bar when the project's documents cannot be read", async () => {
      const documents = () =>
        Promise.reject(new Error("the server answered 500"));
      await renderHome(withOrchestrator(), fakeApi(), FLOW, {
        ...httpProjectApi,
        documents,
      });
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const panel = screen.getByRole("region", { name: "Project" });
      expect(
        await within(panel).findByText(
          /could not read the project's documents: the server answered 500/,
        ),
      ).toBeVisible();
      expect(
        screen.queryByRole("list", { name: "Documents drafted on this turn" }),
      ).toBeNull();
    });

    it("keeps the conversation working when the phases cannot be loaded", async () => {
      const failing: FlowApi = {
        get: () => Promise.reject(new Error("the server answered 500")),
      };
      await renderHome(withOrchestrator(), fakeApi(), failing);
      const phases = screen.getByRole("navigation", {
        name: "Your data journey",
      });
      expect(await within(phases).findByRole("alert")).toHaveTextContent(
        "the server answered 500",
      );
      expect(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
      ).toBeEnabled();
    });

    it("keeps the phases when there is no conversation", async () => {
      await renderHome(normalise(raw), fakeApi());
      expect(
        screen.getByRole("heading", {
          level: 1,
          name: "No conversation is available",
        }),
      ).toBeVisible();
      expect((await screen.findAllByText("Plan ahead"))[0]).toBeVisible();
    });
  });

  describe("the selected run in its card", () => {
    const run = { ...(runFixture as unknown as RunResult) };
    const runs = { get: vi.fn().mockResolvedValue(run) } as unknown as RunApi;

    function renderWithRuns(conversation: Conversation) {
      const api = fakeApi({ get: () => Promise.resolve(conversation) });
      return opened(render(
        <AnnouncerProvider>
          <FlowApiContext.Provider value={FLOW}>
            <RunApiContext.Provider value={runs}>
              <ActiveProjectProvider>
                <ConversationApiContext.Provider value={api}>
                  <ConversationHome directory={withOrchestrator()} />
                </ConversationApiContext.Provider>
              </ActiveProjectProvider>
            </RunApiContext.Provider>
          </FlowApiContext.Provider>
        </AnnouncerProvider>,
      ));
    }

    async function sendAndSelect(conversation: Conversation) {
      history.replaceState(null, "", "/");
      const view = await renderWithRuns(conversation);
      await userEvent.type(
        screen.getByRole("textbox", { name: "What would you like to do?" }),
        "hi",
      );
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      const show = (
        await screen.findAllByRole("button", { name: /Show the run/ })
      )[0] as HTMLElement;
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
      expect(
        await within(card).findByRole("heading", { name: /^Outcome:/ }),
      ).toBeVisible();
      expect(
        within(card).getByRole("heading", { name: /^Evidence/ }),
      ).toBeVisible();
      expect(
        screen.getByRole("list", { name: "Conversation" }),
      ).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
      await userEvent.click(show);
      expect(location.search).toBe("?conversation=c1");
      expect(show).toHaveAttribute("aria-expanded", "false");
      expect(
        within(card).queryByRole("heading", { name: /^Outcome:/ }),
      ).toBeNull();
    });

    it("opens a linked run that is not in the transcript, as after a reload", async () => {
      history.replaceState(null, "", `/?run=${run.envelope.invocation_id}`);
      await renderWithRuns(CONVERSATION);
      const linked = screen.getByRole("region", { name: /^Run / });
      expect(
        await within(linked).findByRole("heading", { name: /^Outcome:/ }),
      ).toBeVisible();
      await userEvent.click(
        within(linked).getByRole("button", { name: "Close the run" }),
      );
      expect(location.search).toBe("");
      expect(screen.queryByRole("region", { name: /^Run / })).toBeNull();
    });

    it("says a suspended child is waiting for review", async () => {
      const suspended = structuredClone(CONVERSATION);
      for (const t of suspended.turns)
        for (const c of t.children) c.outcome.status = "suspended";
      await sendAndSelect(suspended);
      expect(
        (await screen.findAllByText(/Waiting for review/))[0],
      ).toBeVisible();
    });
  });

  describe("where the project is in the journey", () => {
    const LOGGERS = (projectsFixture as ProjectSummary[])[0] as ProjectSummary;
    const flow = flowFixture as ProcessFlow;
    const label = (id: string) => {
      const found = flow.phases
        .flatMap((p) => p.steps)
        .find((s) => s.id === id);
      if (!found) throw new Error(`no step ${id} in the fixture`);
      return found.label;
    };
    const AT_ENTRY_TWO: ProjectProgress = projectProgress({
      entry: 2,
      steps: { "preparation.files": "done" },
      suggested: "governance.policies",
    });

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
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress(),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      expect(await within(phases).findByRole("status")).toHaveTextContent(
        `Suggested next: ${label("governance.policies")}`,
      );
      expect(
        within(phases).getByRole("combobox", { name: "Where you started" }),
      ).toHaveValue("2");
      await userEvent.click(
        within(phases).getByText("Show what happens in each phase"),
      );
      expect(
        within(phases).getByRole("button", {
          name: `Open again: ${label("preparation.files")}`,
        }),
      ).toBeInTheDocument();
      expect(phases).not.toHaveTextContent(/\bR\d|agent/);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("records a step marked, or the entry point chosen, and draws what the server reads back", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const markStep = vi.fn(() =>
        Promise.resolve(
          projectProgress({
            entry: 2,
            steps: {
              "preparation.files": "done",
              "governance.policies": "skipped",
            },
            suggested: "governance.sensitive-data-identify",
          }),
        ),
      );
      const chooseEntry = vi.fn(() =>
        Promise.resolve<ProjectProgress>({ ...AT_ENTRY_TWO, entry: 3 }),
      );
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({ markStep, chooseEntry }),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      await within(phases).findByRole("status");
      await userEvent.click(
        within(phases).getByText("Show what happens in each phase"),
      );
      await userEvent.click(
        within(phases).getByRole("button", {
          name: `Skip: ${label("governance.policies")}`,
        }),
      );
      expect(markStep).toHaveBeenCalledWith(
        LOGGERS.project_id,
        "governance.policies",
        "skipped",
      );
      expect(await within(phases).findByRole("status")).toHaveTextContent(
        label("governance.sensitive-data-identify"),
      );

      await userEvent.selectOptions(
        within(phases).getByRole("combobox", { name: "Where you started" }),
        "3",
      );
      expect(chooseEntry).toHaveBeenCalledWith(LOGGERS.project_id, 3);
    });

    it("suggests nothing for Phase 1 while no entry point is recorded", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const unknown: ProjectProgress = projectProgress();
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({ progress: () => Promise.resolve(unknown) }),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      const status = await within(phases).findByRole("status");
      expect(status).not.toHaveTextContent("Suggested next");
      expect(status).not.toHaveTextContent("done or skipped");
      expect(
        within(phases).getByRole("combobox", { name: "Where you started" }),
      ).toHaveValue("");
    });

    const step = (id: string) => {
      const found = flow.phases
        .flatMap((p) => p.steps)
        .find((s) => s.id === id);
      if (!found) throw new Error(`no step ${id} in the fixture`);
      return found;
    };

    it("starts a new conversation from a step with its prompt in the box, unsent", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      const { container } = await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn }),
        FLOW,
        withProgress(),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      await within(phases).findByRole("status");
      await userEvent.click(
        within(phases).getByText("Show what happens in each phase"),
      );
      // A step done or skipped, or out of scope, offers no conversation.
      expect(
        within(phases).queryByRole("button", {
          name: `Start a conversation: ${label("preparation.files")}`,
        }),
      ).not.toBeInTheDocument();
      expect(
        within(phases).queryByRole("button", {
          name: `Start a conversation: ${label("setup.dmp-create")}`,
        }),
      ).not.toBeInTheDocument();

      const chosen = step("repository.recommend");
      await userEvent.click(
        within(phases).getByRole("button", {
          name: `Start a conversation: ${chosen.label}`,
        }),
      );
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      expect(box).toHaveValue(chosen.prompt);
      await waitFor(() => expect(box).toHaveFocus());
      expect(sendTurn).not.toHaveBeenCalled();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("asks before replacing a message being written", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      await renderHome(withOrchestrator(), fakeApi(), FLOW, withProgress());
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      await within(phases).findByRole("status");
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      await userEvent.type(box, "my own words");
      const suggested = step("governance.policies");
      await userEvent.click(
        within(phases).getAllByRole("button", {
          name: `Start a conversation: ${suggested.label}`,
        })[0] as HTMLElement,
      );
      const dialog = await screen.findByRole("dialog");
      await userEvent.click(
        within(dialog).getByRole("button", { name: "Keep my message" }),
      );
      expect(box).toHaveValue("my own words");

      await userEvent.click(
        within(phases).getAllByRole("button", {
          name: `Start a conversation: ${suggested.label}`,
        })[0] as HTMLElement,
      );
      await userEvent.click(
        within(await screen.findByRole("dialog")).getByRole("button", {
          name: "Replace it",
        }),
      );
      expect(box).toHaveValue(suggested.prompt);
    });

    it("offers ways to start an empty conversation, led by the suggested step", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const sendTurn = vi.fn().mockResolvedValue(undefined);
      await renderHome(
        withOrchestrator(),
        fakeApi({ sendTurn }),
        FLOW,
        withProgress(),
      );
      const offered = await screen.findByRole("group", {
        name: "Suggested ways to start",
      });
      const buttons = within(offered).getAllByRole("button");
      const suggested = step("governance.policies");
      expect(buttons[0]).toHaveAccessibleName(suggested.prompt);
      expect(offered).not.toHaveTextContent(step("preparation.files").prompt);

      await userEvent.click(buttons[0] as HTMLElement);
      const box = screen.getByRole("textbox", {
        name: "What would you like to do?",
      });
      expect(box).toHaveValue(suggested.prompt);
      expect(sendTurn).not.toHaveBeenCalled();
      // With a message in the box, the offer gives way to it.
      expect(
        screen.queryByRole("group", { name: "Suggested ways to start" }),
      ).not.toBeInTheDocument();
    });

    it("offers no ways to start while nothing is suggested", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({
          progress: () => Promise.resolve(projectProgress()),
        }),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      await within(phases).findByRole("status");
      expect(
        screen.queryByRole("group", { name: "Suggested ways to start" }),
      ).not.toBeInTheDocument();
    });

    it("says when Data Director recorded the entry point from what the researcher said", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const read: ProjectProgress = { ...AT_ENTRY_TWO, entry_source: "model" };
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({ progress: () => Promise.resolve(read) }),
      );
      const phases = await screen.findByRole("navigation", {
        name: "Your data journey",
      });
      expect(
        await within(phases).findByText(/Set by Data Director/),
      ).toBeVisible();
      expect(
        within(phases).getByRole("combobox", { name: "Where you started" }),
      ).toHaveValue("2");
    });

    it("asks the intake as soon as New project creates a project, before anything is typed", async () => {
      const created = projectCreatedFixture as unknown as ProjectSummary;
      const pending = intakePendingFixture as ProjectIntake;
      const entry = pending.questions[0];
      if (!entry) throw new Error("the intake fixture asks nothing");
      const listed: ProjectSummary[] = [];
      const create = vi.fn<ProjectApi["create"]>(() => {
        listed.push(created);
        return Promise.resolve(created);
      });
      const intake = vi.fn<ProjectApi["intake"]>(() => Promise.resolve(pending));
      const startConversation = vi.fn();
      await renderHome(
        withOrchestrator(),
        fakeApi({ create: startConversation }),
        FLOW,
        withProgress({ projects: () => Promise.resolve([...listed]), create, intake }),
      );
      await userEvent.click(await screen.findByRole("button", { name: /No project/ }));
      await userEvent.click(await screen.findByRole("option", { name: "New project" }));
      const dialog = await screen.findByRole("dialog", { name: "New project" });
      await userEvent.type(within(dialog).getByRole("textbox"), "Soil cores");
      await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));

      expect(create).toHaveBeenCalledWith("Soil cores");
      expect(
        await screen.findByRole("group", { name: entry.question.question_prompt }),
      ).toBeVisible();
      expect(intake).toHaveBeenCalledWith(created.project_id, expect.anything());
      expect(screen.queryByRole("dialog")).toBeNull();
      // No message was sent, so no conversation was started.
      expect(startConversation).not.toHaveBeenCalled();
      expect(localStorage.getItem("dd-project")).toBe(created.project_id);
    });

    it("opens the New project dialog from a button beside the switcher, without opening the list", async () => {
      await renderHome(withOrchestrator(), fakeApi(), FLOW, withProgress({}));
      await userEvent.click(await screen.findByRole("button", { name: "New project" }));
      expect(await screen.findByRole("dialog", { name: "New project" })).toBeVisible();
      expect(screen.queryByRole("listbox")).toBeNull();
    });

    it("opens a pending project with the intake card and keeps the message box usable", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const pending = intakePendingFixture as ProjectIntake;
      const complete = intakeCompleteFixture as ProjectIntake;
      const entry = pending.questions[0];
      const option = entry?.question.question_options?.[0];
      if (!entry || !option) throw new Error("the intake fixture asks nothing");
      const answerIntake = vi.fn<ProjectApi["answerIntake"]>(() => Promise.resolve(complete));
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({ intake: () => Promise.resolve(pending), answerIntake }),
      );
      const group = await screen.findByRole("group", { name: entry.question.question_prompt });
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toBeEnabled();

      await userEvent.click(within(group).getByRole("radio", { name: option.option_label }));
      await userEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(answerIntake).toHaveBeenCalledWith(LOGGERS.project_id, entry.question_id, [
        option.option_value,
      ]);
      // The tracker moves with the progress the answer came back with.
      const suggested = complete.progress.suggested;
      if (!suggested) throw new Error("the complete fixture suggests nothing");
      const phases = screen.getByRole("navigation", { name: "Your data journey" });
      await waitFor(() =>
        expect(within(phases).getByRole("status")).toHaveTextContent(label(suggested)),
      );
      expect(screen.getByRole("textbox", { name: "What would you like to do?" })).toBeEnabled();
    });

    it("hands a finished intake over to the conversation when the researcher starts", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const pending = intakePendingFixture as ProjectIntake;
      const complete = intakeCompleteFixture as ProjectIntake;
      const entry = pending.questions[0];
      const option = entry?.question.question_options?.[0];
      if (!entry || !option) throw new Error("the intake fixture asks nothing");
      const create = vi.fn<ConversationApi["create"]>(() =>
        Promise.resolve({ conversation_id: "c1", project_id: LOGGERS.project_id }),
      );
      const sendTurn = vi.fn<TurnSent>(() => Promise.resolve());
      await renderHome(
        withOrchestrator(),
        fakeApi({ create, sendTurn }),
        FLOW,
        withProgress({
          intake: () => Promise.resolve(pending),
          answerIntake: () => Promise.resolve(complete),
        }),
      );
      const group = await screen.findByRole("group", { name: entry.question.question_prompt });
      await userEvent.click(within(group).getByRole("radio", { name: option.option_label }));
      await userEvent.click(screen.getByRole("button", { name: "Next" }));
      const suggested = complete.progress.suggested;
      if (!suggested) throw new Error("the complete fixture suggests nothing");
      // No conversation exists until the researcher chooses to start one.
      expect(create).not.toHaveBeenCalled();

      await userEvent.click(
        await screen.findByRole("button", { name: `Start with ${label(suggested)}` }),
      );
      await waitFor(() => expect(sendTurn).toHaveBeenCalledTimes(1));
      expect(create).toHaveBeenCalledWith(LOGGERS.project_id);
      expect(sendTurn).toHaveBeenCalledWith(
        "c1",
        turnBody(
          expect.any(String),
          expect.stringContaining(label(suggested)),
          null,
          null,
          null,
          null,
        ),
      );
      expect(screen.queryByRole("heading", { name: "Where your project starts" })).toBeNull();
    });

    it("shows no card for a complete intake until the tracker asks the questions again", async () => {
      localStorage.setItem("dd-project", LOGGERS.project_id);
      const complete = intakeCompleteFixture as ProjectIntake;
      await renderHome(
        withOrchestrator(),
        fakeApi(),
        FLOW,
        withProgress({ intake: () => Promise.resolve(complete) }),
      );
      const again = await screen.findByRole("button", { name: "Answer the setup questions again" });
      const first = complete.questions[0];
      if (!first) throw new Error("the intake fixture asks nothing");
      expect(screen.queryByRole("group", { name: first.question.question_prompt })).toBeNull();
      await userEvent.click(again);
      expect(
        await screen.findByRole("group", { name: first.question.question_prompt }),
      ).toBeInTheDocument();
    });
  });

  describe("the run, drawn live from its stream", () => {
    /** Sends "hi" with turns replayed from `events`, `paceMs` apart. */
    async function sendWith(events: readonly unknown[], paceMs = 0) {
      const api = { ...fakeApi(), turns: cassetteTransport(events, { paceMs }) };
      const view = await renderHome(withOrchestrator(), api);
      await userEvent.type(screen.getByRole("textbox"), "hi");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      return { ...view, api };
    }

    const progress = () => screen.getByRole("region", { name: "Progress" });
    const stage = (label: string) =>
      within(progress()).getByText(label).closest("li") as HTMLElement;
    const upTo = (type: string) =>
      SUCCEEDED.slice(0, SUCCEEDED.findIndex((e) => (e as { type: string }).type === type) + 1);

    it("updates each stage as the stream arrives, then shows the reply as a turn", async () => {
      const { container } = await sendWith(SUCCEEDED, 40);
      await waitFor(() => expect(stage("Policy gate")).toHaveTextContent("Running"));
      expect(stage("Source check")).toHaveTextContent("Waiting");
      expect(await axe(container)).toHaveNoViolations();
      await waitFor(() => expect(stage("Policy gate")).toHaveTextContent("Done"));
      // Once the run has finished, the reply is a turn of the transcript and the run goes.
      await waitFor(() => expect(screen.queryByRole("region", { name: "Progress" })).toBeNull(), {
        timeout: 3000,
      });
      const transcript = screen.getByRole("list", { name: "Conversation" });
      expect(transcript.querySelectorAll(".turn-agent .turn-speaker-name").length).toBeGreaterThan(0);
      expect(screen.getByRole("textbox")).toHaveFocus();
    });

    it("cancels the run, and lands on the cancelled screen", async () => {
      const { container } = await sendWith(SUCCEEDED, 100);
      const cancel = await screen.findByRole("button", { name: "Cancel the run" });
      await userEvent.click(cancel);
      const heading = await screen.findByRole("heading", { name: /Outcome: Cancelled/ });
      await waitFor(() => expect(heading).toHaveFocus());
      expect(screen.queryByRole("button", { name: "Cancel the run" })).toBeNull();
      // No stage is left running or waiting once the run is cancelled.
      expect(within(progress()).queryByText("Running")).toBeNull();
      expect(within(progress()).queryByText("Waiting")).toBeNull();
      expect(within(announcements()).getByText("Run cancelled.")).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("lands on the interrupted screen when the stream closes before the run ends", async () => {
      const { container } = await sendWith(upTo("STEP_STARTED"));
      const heading = await screen.findByRole("heading", { name: /Outcome: Interrupted/ });
      await waitFor(() => expect(heading).toHaveFocus());
      expect(stage("Policy gate")).toHaveTextContent("Stopped");
      expect(stage("Agent")).toHaveTextContent("Not reached");
      // Nothing invents a finish: the reply is not announced.
      expect(within(announcements()).queryByText(/Run finished/)).toBeNull();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("shows a run that failed once it had started, with the reason the stream gave", async () => {
      const failed = [...upTo("STEP_STARTED"), { type: "RUN_ERROR", message: "The agent crashed." }];
      const { container } = await sendWith(failed);
      expect(await screen.findByRole("heading", { name: /Outcome: Failed/ })).toBeVisible();
      expect(screen.getByText("The agent crashed.")).toBeVisible();
      // It ran, so the message is not offered to be sent again.
      expect(screen.getByRole("textbox")).toHaveValue("");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("gives the message back when the server refuses the turn once its stream is open", async () => {
      await sendWith([{ type: "RUN_ERROR", message: "No such agent." }]);
      expect(await screen.findByRole("alert")).toHaveTextContent("No such agent.");
      expect(screen.getByRole("textbox")).toHaveValue("hi");
      expect(screen.queryByRole("region", { name: "Progress" })).toBeNull();
    });
  });
});
