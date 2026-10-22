import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import conversationFixture from "../../../fixtures/conversation.json";
import { type ConversationApi, ConversationApiContext } from "../../conversation/api";
import type { Conversation } from "../../conversation/types";
import { type Directory, normalise } from "../../manifest/normalise";
import type { RawAgentsResponse, RawManifestEntry } from "../../manifest/types";
import { ConversationHome } from "./ConversationHome";

const CONVERSATION = conversationFixture as unknown as Conversation;
const raw = several as unknown as RawAgentsResponse;
const template: RawManifestEntry | undefined = raw.agents[0];
if (!template) throw new Error("no agent in the fixture");

/** The several-agents set plus an orchestrator, found by its grounding mode. */
function withOrchestrator(assigned: string | null = "advise"): Directory {
  return normalise({
    ...raw,
    agents: [
      ...raw.agents,
      { ...(template as RawManifestEntry), agent_id: "director.stub", grounding_mode: "delegation", assigned_action_class: assigned },
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

function renderHome(directory: Directory, api: ConversationApi) {
  return render(
    <ConversationApiContext.Provider value={api}>
      <ConversationHome directory={directory} />
    </ConversationApiContext.Provider>,
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

  it("says when the profile does not permit the orchestrator", () => {
    renderHome(withOrchestrator(null), fakeApi());
    expect(screen.getByText(/does not permit director.stub/)).toBeVisible();
  });

  it("sends a turn, labels replies and children, and returns focus to the message box", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { container } = renderHome(withOrchestrator(), fakeApi({ sendTurn }));
    expect(screen.getByText(/acts for .*not\s+authenticated/)).toBeVisible();
    const box = screen.getByRole("textbox", { name: "What would you like to do?" });
    await userEvent.type(box, "hello world");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(sendTurn).toHaveBeenCalledWith("c1", "director.stub", "hello world");
    const transcript = await screen.findByRole("list", { name: "Conversation" });
    expect(within(transcript).getAllByText("director.stub@0.1.0")).toHaveLength(2);
    expect(within(transcript).getAllByText("hello.world@0.1.0")).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("New reply from director.stub: Succeeded.");
    expect(box).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks a version change between turns", async () => {
    const changed: Conversation = {
      ...CONVERSATION,
      version_changes: [{ turn_index: 1, agent_id: "director.stub", from: "0.1.0", to: "0.2.0" }],
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
  });

  it("reopens a past conversation and starts a new one", async () => {
    const list = () =>
      Promise.resolve([
        { conversation_id: "c9", agent_id: "director.stub", turns: 2, started_at: "2026-01-01" },
      ]);
    renderHome(withOrchestrator(), fakeApi({ list }));
    await userEvent.click(await screen.findByRole("button", { name: /2026-01-01 \(2 turns\)/ }));
    expect(await screen.findByRole("list", { name: "Conversation" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();
  });
});
