/**
 * The open conversation and its turns: which conversation is open, kept in the address
 * (`?conversation=`) so that a reload or a link reopens it; the project's earlier conversations;
 * and sending a turn to the orchestrator (docs/specs/app.md, docs/specs/orchestration.md).
 *
 * A turn is streamed (`useTurnStream`): its run is drawn live while the reply is awaited, and can
 * be cancelled. A run that finished is shown as a turn, read back once the stream has closed; one
 * that was cancelled, failed or was cut short stays in place with its own screen until the next
 * message, beside whatever the server stored of it.
 *
 * While a reply is awaited the message sits in the transcript; it comes back to the message box if
 * the send fails, so nothing typed or attached is lost, but not once the turn is stored, so that it
 * is never sent twice (#337). Each turn names the latest turn the page shows, and the server
 * refuses one that does not follow it. Switching project closes the open conversation; starting a
 * project by sending the first message does not, since the open conversation is the one that
 * started it.
 */

import { type RefObject, useEffect, useRef, useState } from "react";

import {
  TurnConflict,
  Unreachable,
  useConversationApi,
  type ConversationApi,
} from "../../conversation/api";
import type { ReplyAnswers } from "../../conversation/question";
import type { Conversation, ConversationSummary } from "../../conversation/types";
import { useActiveProject } from "../../project/active";
import { homePath, navigate } from "../../route";
import { errorMessage } from "../../run/api";
import type { RunState } from "../../run/reduce";
import { useResource } from "../../useResource";
import type { Carried } from "./useAttachments";
import type { AwaitedDrafts } from "./useProjectDocuments";
import { body, refusedInStream, replyAnnouncement, sendFailure } from "./turnMessages";
import { useTurnStream } from "./useTurnStream";

export { replyAnnouncement, sendFailure } from "./turnMessages";

/** A message on its way, shown in the transcript until the reply arrives. */
export interface Sent extends Carried {
  message: string;
}

/** The run of the turn being sent, or of the last one if it did not finish. */
export interface LiveRun {
  state: RunState;
  cancelling: boolean;
  /** Cancels the run while it is streaming. */
  cancel(): void;
  /** The server has stored the turn, so the transcript shows the message already. */
  stored: boolean;
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
  /** The run of the message sent, while it is drawn; null once it is shown as a turn. */
  live: LiveRun | null;
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

/** A message with nothing typed and nothing attached. */
function isEmpty(message: string, carried: Carried): boolean {
  return !message && !carried.inventory && !carried.document;
}

/** The latest turn the page shows, by its run's id; null before the first. */
function latestTurn(conversation: Conversation | null): string | null {
  return conversation?.turns[conversation.turns.length - 1]?.invocation_id ?? null;
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
  const turn = useTurnStream();
  // How many turns the conversation held when the message was sent.
  const [sentAfter, setSentAfter] = useState(0);
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
    if (!busy) dropLive();
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    setError(null);
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
  }

  /** The message moves into the transcript while the reply is awaited, and out of the box. */
  function begin(sending: Sent, fromBox: boolean) {
    setBusy(true);
    setError(null);
    options.clearAttachError();
    turn.clear();
    setSent(sending);
    setSentAfter(conversation?.turns.length ?? 0);
    if (fromBox) {
      setText("");
      options.restore(NOTHING);
    }
  }

  /** The run has ended and the conversation has been read again. A finished run is shown as a
   * turn; any other keeps its own screen, beside what the server stored. */
  function shown(ended: RunState, updated: Conversation) {
    if (ended.phase === "finished") {
      turn.clear();
      replied(updated);
      return;
    }
    setConversation(updated);
    reloadPast();
    reloadProjects();
  }

  /** The turn ran, but the conversation could not be read again to show it. */
  function notShown(e: unknown) {
    reloadPast();
    reloadProjects();
    setError(
      "Your message was sent and answered, but Data Director could not show the reply " +
        `(${errorMessage(e)}). Open this conversation from Conversations to see it.`,
    );
  }

  async function deliver(message: string, carried: Carried, answer: ReplyAnswers | null) {
    if (!orchestratorId || isEmpty(message, carried) || busy) return;
    // A typed message comes from the box, and goes back to it if the send fails.
    const fromBox = answer === null;
    begin({ message, ...carried }, fromBox);
    let id = conversationId;
    let ended: RunState | null = null;
    // The latest turn this page shows: the server refuses the turn if the conversation has
    // moved on since, so a message sent again after a dropped connection never runs twice.
    const follows = latestTurn(conversation);
    try {
      id ??= await start();
      setConversationId(id);
      const run = await turn.stream(id, body(orchestratorId, message, follows, carried, answer));
      if (refusedInStream(run)) throw new Error(run.error ?? "the turn was refused");
      // The turn has run: from here a failure is in showing the reply, not in sending it, so the
      // message must not come back to the box to be sent twice (#337).
      ended = run;
      shown(run, await readReply(api, id));
    } catch (e) {
      if (ended) notShown(e);
      else {
        turn.clear();
        notSent(e, id, fromBox ? { message, ...carried } : null);
      }
    } finally {
      // A run that did not finish keeps its screen, whose heading has the focus.
      if (ended?.phase === "finished" || ended === null) {
        setSent(null);
        box.current?.focus();
      }
      setBusy(false);
    }
  }

  /** Lets the last message's run go, as when another conversation is shown. */
  function dropLive() {
    setSent(null);
    turn.clear();
  }

  async function reopen(id: string) {
    dropLive();
    try {
      open(id, await api.get(id));
      navigate(homePath({ conversation: id }));
      box.current?.focus();
    } catch (e) {
      setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
    }
  }

  function reset() {
    dropLive();
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    handled.current = null;
    if (runId || urlConversation) navigate("/");
    setError(null);
    setText("");
    options.restore(NOTHING);
    options.clearAttachError();
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
    live: turn.run && {
      state: turn.run,
      cancelling: turn.cancelling,
      cancel: turn.cancel,
      stored: turnCount > sentAfter,
    },
    awaitedDrafts,
    error,
    setError,
    deliver,
    reopen,
    reset,
  };
}
