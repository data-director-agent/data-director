import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import conversationFixture from "../../../fixtures/conversation.json";
import questionFixture from "../../../fixtures/conversation-question.json";
import {
  type ConversationApi,
  ConversationApiContext,
  TurnConflict,
  Unreachable,
} from "../../conversation/api";
import type { Conversation } from "../../conversation/types";
import { ActiveProjectProvider } from "../../project/active";
import { type ProjectApi, ProjectApiContext } from "../../project/api";
import { RunRefused } from "../../run/api";
import type { Carried } from "./useAttachments";
import {
  replyAnnouncement,
  sendFailure,
  type TurnsOptions,
  useConversationTurns,
} from "./useConversationTurns";

const CONVERSATION = conversationFixture as unknown as Conversation;
const QUESTION = questionFixture as unknown as Conversation;
const NOTHING: Carried = { inventory: null, document: null };
const CONFLICT = new TurnConflict({
  type: "https://example.org/turn-conflict",
  title: "The conversation has moved on",
  http_status: 409,
});

// The project the conversations are in, which the workspace follows when one is opened.
const PROJECTS = {
  projects: () => Promise.resolve([{ project_id: CONVERSATION.project_id }]),
} as unknown as ProjectApi;

function fakeApi(overrides: Partial<ConversationApi> = {}): ConversationApi {
  return {
    create: () => Promise.resolve({ conversation_id: "c1", project_id: null }),
    sendTurn: () => Promise.resolve(),
    list: () => Promise.resolve([]),
    get: () => Promise.resolve(CONVERSATION),
    ...overrides,
  };
}

function renderTurns(api: ConversationApi, options: Partial<TurnsOptions> = {}) {
  const props: TurnsOptions = {
    orchestratorId: "orchestrator.stub",
    runId: null,
    urlConversation: null,
    box: { current: null },
    announce: vi.fn(),
    setText: vi.fn(),
    restore: vi.fn(),
    clearAttachError: vi.fn(),
    ...options,
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ProjectApiContext.Provider value={PROJECTS}>
      <ActiveProjectProvider>
        <ConversationApiContext.Provider value={api}>{children}</ConversationApiContext.Provider>
      </ActiveProjectProvider>
    </ProjectApiContext.Provider>
  );
  const view = renderHook(() => useConversationTurns(props), { wrapper });
  return { ...view, props };
}

describe("useConversationTurns", () => {
  beforeEach(() => {
    history.replaceState(null, "", "/");
    localStorage.clear();
  });

  it("starts a conversation, sends the turn and holds the reply", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { result, props } = renderTurns(fakeApi({ sendTurn }));
    await act(() => result.current.deliver("hi", NOTHING, null));
    expect(sendTurn).toHaveBeenCalledWith("c1", "orchestrator.stub", "hi", null, null);
    expect(result.current.conversation).toEqual(CONVERSATION);
    expect(result.current.conversationId).toBe("c1");
    expect(result.current.turnCount).toBe(CONVERSATION.turns.length);
    expect(result.current.busy).toBe(false);
    expect(result.current.awaitedDrafts?.invocationIds).toContain(
      CONVERSATION.turns.at(-1)?.invocation_id,
    );
    expect(props.setText).toHaveBeenCalledWith("");
    expect(location.search).toContain("conversation=c1");
  });

  it("names the latest turn it shows as the one a new turn follows", async () => {
    const sendTurn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderTurns(fakeApi({ sendTurn }));
    await act(() => result.current.deliver("hi", NOTHING, null));
    await act(() => result.current.deliver("and again", NOTHING, null));
    const latest = CONVERSATION.turns.at(-1)?.invocation_id;
    expect(latest).toBeDefined();
    expect(sendTurn).toHaveBeenLastCalledWith("c1", "orchestrator.stub", "and again", latest, null);
  });

  it("sends nothing without an orchestrator or anything to send", async () => {
    const sendTurn = vi.fn();
    const { result } = renderTurns(fakeApi({ sendTurn }), { orchestratorId: undefined });
    await act(() => result.current.deliver("hi", NOTHING, null));
    const other = renderTurns(fakeApi({ sendTurn }));
    await act(() => other.result.current.deliver("", NOTHING, null));
    expect(sendTurn).not.toHaveBeenCalled();
  });

  it("holds the message as sent while the reply is awaited", async () => {
    let reply: () => void = () => undefined;
    const sendTurn = () => new Promise<void>((resolve) => (reply = resolve));
    const { result } = renderTurns(fakeApi({ sendTurn }));
    let sending: Promise<void> = Promise.resolve();
    act(() => {
      sending = result.current.deliver("hello", NOTHING, null);
    });
    await waitFor(() => expect(result.current.sent?.message).toBe("hello"));
    expect(result.current.busy).toBe(true);
    expect(result.current.quiet).toBe(false);
    await act(async () => {
      reply();
      await sending;
    });
    expect(result.current.sent).toBeNull();
  });

  it("gives a failed message back to the box, with what it carried", async () => {
    const carried: Carried = {
      inventory: null,
      document: { name: "a.md", media_type: "text/markdown", text: "# A", size: 3 },
    };
    const { result, props } = renderTurns(
      fakeApi({ sendTurn: () => Promise.reject(new Error("the server answered 500")) }),
    );
    await act(() => result.current.deliver("hi", carried, null));
    expect(result.current.error).toBeTruthy();
    expect(props.setText).toHaveBeenLastCalledWith("hi");
    expect(props.restore).toHaveBeenLastCalledWith(carried);
    expect(result.current.sent).toBeNull();
  });

  it("does not give back an answer to a question, which did not come from the box", async () => {
    const { result, props } = renderTurns(
      fakeApi({ sendTurn: () => Promise.reject(new Error("down")) }),
    );
    const answers = { answer_to: "q", answers: [] } as never;
    await act(() => result.current.deliver("yes", NOTHING, answers));
    expect(props.setText).not.toHaveBeenCalled();
  });

  it.each([
    ["the server could not be reached", new Unreachable()],
    ["the conversation has moved on", CONFLICT],
  ])("reads the conversation again when %s", async (_, failure) => {
    const get = vi.fn().mockResolvedValue(CONVERSATION);
    const { result } = renderTurns(fakeApi({ sendTurn: () => Promise.reject(failure), get }));
    await act(() => result.current.deliver("hi", NOTHING, null));
    expect(get).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(result.current.conversation).toEqual(CONVERSATION));
    expect(result.current.error).toBe(sendFailure(failure));
  });

  it("reads the reply again when the first read after a turn gets no response", async () => {
    const get = vi.fn().mockRejectedValueOnce(new Unreachable()).mockResolvedValue(CONVERSATION);
    const { result } = renderTurns(fakeApi({ get }));
    await act(() => result.current.deliver("hi", NOTHING, null));
    expect(get).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
    expect(result.current.conversation).toEqual(CONVERSATION);
  });

  it("does not offer a stored turn to be sent again when its reply cannot be shown", async () => {
    const { result, props } = renderTurns(
      fakeApi({ get: () => Promise.reject(new Unreachable()) }),
    );
    await act(() => result.current.deliver("hi", NOTHING, null));
    expect(result.current.error).toBeTruthy();
    expect(result.current.error).not.toBe(sendFailure(new Unreachable()));
    expect(props.setText).not.toHaveBeenCalledWith("hi");
  });

  it("reopens a past conversation and starts a new one", async () => {
    const get = vi.fn().mockResolvedValue(CONVERSATION);
    const { result, props } = renderTurns(fakeApi({ get }));
    await act(() => result.current.reopen("c9"));
    expect(get).toHaveBeenCalledWith("c9");
    expect(result.current.conversationId).toBe("c9");
    expect(location.search).toContain("conversation=c9");
    act(() => result.current.reset());
    expect(result.current.conversation).toBeNull();
    expect(result.current.quiet).toBe(true);
    expect(props.restore).toHaveBeenLastCalledWith(NOTHING);
  });

  it("says when a past conversation cannot be opened", async () => {
    const { result } = renderTurns(fakeApi({ get: () => Promise.reject(new Error("gone")) }));
    await act(() => result.current.reopen("c9"));
    expect(result.current.error).toMatch(/gone/);
    expect(result.current.conversation).toBeNull();
  });

  it("opens the conversation the address names", async () => {
    const get = vi.fn().mockResolvedValue(CONVERSATION);
    const { result } = renderTurns(fakeApi({ get }), { urlConversation: "c7" });
    await waitFor(() => expect(result.current.conversationId).toBe("c7"));
    expect(get).toHaveBeenCalledWith("c7", expect.any(AbortSignal));
  });

  it("lists the earlier conversations, and reads them again after a turn", async () => {
    const list = vi.fn().mockResolvedValue([{ conversation_id: "c0", project_id: null }]);
    const { result } = renderTurns(fakeApi({ list }));
    await waitFor(() => expect(result.current.past).toHaveLength(1));
    await act(() => result.current.deliver("hi", NOTHING, null));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });
});

describe("replyAnnouncement", () => {
  it("says nothing without a turn", () => {
    expect(replyAnnouncement(undefined)).toBe("");
  });

  it("names the agent, and the question a reply asks", () => {
    const plain = replyAnnouncement(CONVERSATION.turns.at(-1));
    const asking = replyAnnouncement(QUESTION.turns.at(-1));
    expect(plain).toContain("orchestrator.stub");
    expect(asking.startsWith(plain.split(":")[0] ?? "")).toBe(true);
    expect(asking.length).toBeGreaterThan(plain.length - 1);
  });
});

describe("sendFailure", () => {
  it("tells apart each way a send fails", () => {
    const refused = new RunRefused({ type: "about:blank", title: "Refused", detail: "no" });
    const said = [new Unreachable(), CONFLICT, refused, new Error("boom")].map(sendFailure);
    expect(new Set(said).size).toBe(said.length);
    expect(said[2]).toContain("Refused");
  });
});
