/**
 * The open conversation and its turns: which conversation is open, kept in the address
 * (`?conversation=`) so that a reload or a link reopens it; the project's earlier conversations;
 * and sending a turn to the orchestrator (docs/specs/app.md, docs/specs/orchestration.md).
 *
 * While a reply is awaited the message sits in the transcript; it comes back to the message box if
 * the send fails, so nothing typed or attached is lost, but not once the turn is stored, so that it
 * is never sent twice (#337). Each turn names the latest turn the page shows, and the server
 * refuses one that does not follow it. Switching project closes the open conversation; starting a
 * project by sending the first message does not, since the open conversation is the one that
 * started it.
 */

import { type RefObject, useEffect, useRef, useState } from "react";

import { NoAnswer, TurnConflict, Unreachable, useConversationApi, type ConversationApi } from "../../conversation/api";
import { type ReplyAnswers, replyQuestions } from "../../conversation/question";
import type { Conversation, ConversationSummary, ConversationTurn } from "../../conversation/types";
import { OUTCOME } from "../../manifest/wording";
import { useActiveProject } from "../../project/active";
import { homePath, navigate } from "../../route";
import { RunRefused, errorMessage } from "../../run/api";
import { useResource } from "../../useResource";
import type { Carried } from "./useAttachments";
import type { AwaitedDrafts } from "./useProjectDocuments";

/** A message on its way, shown in the transcript until the reply arrives. */
export interface Sent extends Carried {
  message: string;
}

export interface TurnsOptions {
  /** The agent conversed with, if there is one to converse with. */
  orchestratorId: string | undefined;
  runId: string | null;
  /** The conversation the address names. */
  urlConversation: string | null;
  box: RefObject<HTMLTextAreaElement | null>;
  announce(said: string): void;
  /** Puts text in the message box. */
  setText(text: string): void;
  /** Puts what a message carries back on the next one, as after a failed send. */
  restore(carried: Carried): void;
  clearAttachError(): void;
}

export interface Turns {
  conversation: Conversation | null;
  conversationId: string | null;
  /** How many turns the open conversation shows. */
  turnCount: number;
  /** Nothing is being sent and no turn is shown: the conversation has yet to begin. */
  quiet: boolean;
  /** The earlier conversations, in every project. */
  past: ConversationSummary[];
  busy: boolean;
  sent: Sent | null;
  /** The newest reply's announcement and the runs it made, to say what they drafted too. */
  awaitedDrafts: AwaitedDrafts | null;
  error: string | null;
  setError(error: string | null): void;
  /** Sends a turn; with no `answer`, the message came from the box and goes back to it on failure. */
  deliver(message: string, carried: Carried, answer: ReplyAnswers | null): Promise<void>;
  reopen(id: string): Promise<void>;
  /** A new conversation, with nothing in the message box. */
  reset(): void;
}

const NOTHING: Carried = { inventory: null, document: null };

/** What the newest turn's reply says, as announced. */
export function replyAnnouncement(last: ConversationTurn | undefined): string {
  if (!last) return "";
  const asks = replyQuestions(last.envelope);
  const said = `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.`;
  if (asks.length === 1) return `${said} It asks: ${asks[0]?.question_prompt}`;
  if (asks.length > 1) return `${said} It asks you ${asks.length} questions, one at a time.`;
  return said;
}

/** Why a turn could not be sent, for one that was not stored. */
export function sendFailure(e: unknown): string {
  if (e instanceof NoAnswer) {
    return (
      `Data Director's server did not answer in time (it answered ${e.status}), so this ` +
      "message may not have been sent, or may still be being answered. Your message is " +
      "kept: check the conversation above, and send it again if no reply appears. " +
      "Sending it again is safe, because a message that was received is not run twice."
    );
  }
  if (e instanceof Unreachable) {
    return (
      "Data Director could not reach the server, so this message may not have been sent. " +
      "Your message is kept: sending it again is safe, because a message that was " +
      "received is not run twice."
    );
  }
  if (e instanceof TurnConflict) {
    return (
      "This conversation has changed since you wrote this: another message was answered or " +
      "is still being answered. Your message is kept. Check the conversation above, then " +
      "send it again if it is still needed."
    );
  }
  return e instanceof RunRefused
    ? `${e.problem.title}: ${e.message}`
    : `Data Director could not send this: ${errorMessage(e)}`;
}

/** Sends one turn, with the answer or the document only when there is one. */
function sendTurn(
  api: ConversationApi,
  id: string,
  agentId: string,
  message: string,
  follows: string | null,
  carried: Carried,
  answer: ReplyAnswers | null,
): Promise<void> {
  const inventory = carried.inventory?.document ?? null;
  if (answer) return api.sendTurn(id, agentId, message, follows, inventory, undefined, answer);
  if (carried.document) {
    return api.sendTurn(id, agentId, message, follows, inventory, undefined, null, carried.document);
  }
  return api.sendTurn(id, agentId, message, follows, inventory);
}

/** Reads the conversation after a turn, once more if the first read gets no response. */
function readReply(api: ConversationApi, id: string): Promise<Conversation> {
  return api.get(id).catch((e: unknown) => {
    if (e instanceof Unreachable) return api.get(id);
    throw e;
  });
}

export function useConversationTurns(options: TurnsOptions): Turns {
  const { orchestratorId, runId, urlConversation, box, announce, setText } = options;
  const api = useConversationApi();
  const { projectId, setProjectId, reloadProjects } = useActiveProject();
  const [conversationId, setConversationId] = useState<string | null>(null);
  // The project of the open conversation, once it has been started or reopened.
  const [openProject, setOpenProject] = useState<string | null | undefined>(undefined);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [awaitedDrafts, setAwaitedDrafts] = useState<AwaitedDrafts | null>(null);
  const pastRead = useResource("conversations", (_, signal) => api.list(signal));
  const past = pastRead.latest ?? [];
  const reloadPast = pastRead.reload;
  // The conversation the page already holds, or has deliberately closed, so that the address
  // changing to it is not read as a request to load it.
  const handled = useRef<string | null>(null);

  /** Holds `found`, opened in its own project, so the workspace follows it there. */
  function open(id: string, found: Conversation) {
    handled.current = id;
    setConversation(found);
    setConversationId(id);
    setOpenProject(found.project_id ?? null);
    if ((found.project_id ?? null) !== projectId) setProjectId(found.project_id ?? null);
    setError(null);
  }

  // A conversation closed by switching project is taken out of the address, and not read again
  // from it. This runs before the effect below, which would otherwise reopen it.
  const [closed, setClosed] = useState<{ id: string } | null>(null);
  useEffect(() => {
    if (closed === null) return;
    handled.current = closed.id;
    navigate(homePath({ run: runId }), true);
    // Only a closing is acted on; the run is read as it is then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closed]);

  // A conversation named in the address and not yet held, as after a reload or Back, is read and
  // opened in its own project.
  useEffect(() => {
    if (!urlConversation) {
      handled.current = null;
      return;
    }
    if (urlConversation === handled.current) return;
    const id = urlConversation;
    const abort = new AbortController();
    handled.current = id;
    api.get(id, abort.signal).then(
      (found) => open(id, found),
      (e: unknown) => {
        if (abort.signal.aborted) return;
        handled.current = null;
        setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
        navigate(homePath({ run: runId }), true);
      },
    );
    return () => abort.abort();
    // Only the address decides what is loaded; the project is read as it is when the read lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, urlConversation]);

  // Switching project closes the conversation open in another.
  if (openProject !== undefined && openProject !== projectId) {
    if (urlConversation) setClosed({ id: urlConversation });
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    setError(null);
    announce("");
  }

  /** Starts a conversation in the project being worked in, or in a new one the server starts. */
  async function start(): Promise<string> {
    const started = await api.create(projectId);
    const id = started.conversation_id;
    setOpenProject(started.project_id);
    // With no project active, the server started one: the shell is now working in it.
    if (started.project_id !== projectId) setProjectId(started.project_id);
    handled.current = id;
    navigate(homePath({ conversation: id, run: runId }), true);
    return id;
  }

  /** The reply has arrived: it is shown, announced once the documents are read again. */
  function replied(updated: Conversation) {
    const last = updated.turns[updated.turns.length - 1];
    const said = replyAnnouncement(last);
    setAwaitedDrafts(
      last
        ? { said, invocationIds: [last.invocation_id, ...last.children.map((c) => c.invocation_id)] }
        : null,
    );
    setConversation(updated);
    announce(said);
    reloadPast();
    reloadProjects();
  }

  /** The turn was not stored: the message goes back to the box, and the page says why. */
  function notSent(e: unknown, id: string | null, back: Sent | null) {
    if (back) {
      setText(back.message);
      options.restore({ inventory: back.inventory, document: back.document });
    }
    // The server may have received the turn and be running it, or have moved on: show what it
    // stored.
    if (id && (e instanceof Unreachable || e instanceof TurnConflict)) {
      api.get(id).then(setConversation, () => undefined);
    }
    setError(sendFailure(e));
    announce("");
  }

  async function deliver(message: string, carried: Carried, answer: ReplyAnswers | null) {
    if (!orchestratorId || (!message && !carried.inventory && !carried.document) || busy) return;
    // A typed message comes from the box, and goes back to it if the send fails.
    const fromBox = answer === null;
    setBusy(true);
    setError(null);
    options.clearAttachError();
    announce("Waiting for a reply.");
    // The message and what it carries move into the transcript while the reply is awaited.
    setSent({ message, ...carried });
    if (fromBox) {
      setText("");
      options.restore(NOTHING);
    }
    let id = conversationId;
    let stored = false;
    // The latest turn this page shows: the server refuses the turn if the conversation has
    // moved on since, so a message sent again after a dropped connection never runs twice.
    const follows = conversation?.turns[conversation.turns.length - 1]?.invocation_id ?? null;
    try {
      id ??= await start();
      setConversationId(id);
      await sendTurn(api, id, orchestratorId, message, follows, carried, answer);
      // The turn is stored: from here a failure is in showing the reply, not in sending it, so
      // the message must not come back to the box to be sent twice (#337).
      stored = true;
      replied(await readReply(api, id));
    } catch (e) {
      if (stored) {
        reloadPast();
        reloadProjects();
        setError(
          "Your message was sent and answered, but Data Director could not show the reply " +
            `(${errorMessage(e)}). Open this conversation from Conversations to see it.`,
        );
        announce("");
      } else {
        notSent(e, id, fromBox ? { message, ...carried } : null);
      }
    } finally {
      setSent(null);
      setBusy(false);
      box.current?.focus();
    }
  }

  async function reopen(id: string) {
    try {
      open(id, await api.get(id));
      navigate(homePath({ conversation: id }));
      box.current?.focus();
    } catch (e) {
      setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
    }
  }

  function reset() {
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    handled.current = null;
    if (runId || urlConversation) navigate("/");
    setError(null);
    setText("");
    options.restore(NOTHING);
    options.clearAttachError();
    announce("");
    box.current?.focus();
  }

  const turnCount = conversation?.turns.length ?? 0;
  return {
    conversation,
    conversationId,
    turnCount,
    quiet: !busy && sent === null && turnCount === 0,
    past,
    busy,
    sent,
    awaitedDrafts,
    error,
    setError,
    deliver,
    reopen,
    reset,
  };
}
