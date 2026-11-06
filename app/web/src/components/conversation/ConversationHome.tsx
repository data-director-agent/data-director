/**
 * The home page: a conversation with the orchestrator (docs/specs/app.md), in the centre of the
 * workspace (§18), with the person's conversations on the left, an overview of the project on the
 * right and the Blueprint's phases in a strip above. A delegated run opens inside its card in the
 * transcript (§14).
 *
 * The orchestrator is the agent the profile names (docs/specs/app.md), never one the shell picks.
 * When the profile names none, the named agent is not running, its card does not declare
 * `delegation` grounding, or the policy does not permit it, the page says which and links to the
 * directory (§12). The server builds each turn's history; the page sends the agent, the message
 * and the turn it follows, the latest one the page shows (docs/specs/orchestration.md).
 * Until there is authentication (#17) the conversation acts for the operator (docs/specs/policy-and-identity.md).
 *
 * While a reply is awaited the message sits in the transcript beside a pulsing sign that the
 * orchestrator is working. A new reply is announced in a polite live region, the busy state is
 * announced, and focus returns to the message box.
 *
 * A reply may ask a choice question, which the transcript shows as choices; sending the answer
 * takes the same path as a typed message, with the answer beside the labels chosen. The message
 * box stays usable, so the researcher may ignore the question and type instead.
 *
 * A message may attach a `dd-inventory` file, chosen with the Attach button, dropped on the form
 * or pasted, which shows as a chip and goes to the conversation's project, never into the text
 * (#443, docs/specs/app.md). A link beside the button says how to make one.
 */

import {
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { Paperclip, SendHorizontal, X } from "lucide-react";
import { FileTrigger } from "react-aria-components";
import { TurnConflict, Unreachable, useConversationApi } from "../../conversation/api";
import { type ChoiceAnswer, replyQuestion } from "../../conversation/question";
import {
  type AttachedInventory,
  INVENTORY_GUIDE,
  NotAnInventory,
  looksLikeInventory,
  readInventory,
} from "../../conversation/inventory";
import { useFlowApi } from "../../flow/api";
import type { Conversation, ConversationSummary } from "../../conversation/types";
import type { AgentView, Directory } from "../../manifest/normalise";
import { Link, navigate, useLocation } from "../../route";
import { OUTCOME } from "../../manifest/wording";
import { RunRefused, errorMessage } from "../../run/api";
import type { Envelope } from "../../run/types";
import { ContextPanel } from "../workspace/ContextPanel";
import { type FlowLoad, PhaseTracker } from "../workspace/PhaseTracker";
import { Workspace } from "../workspace/Workspace";
import { Button } from "../ui/Button";
import { EarlierConversations } from "./EarlierConversations";
import { InventoryChip } from "./InventoryChip";
import { RunDetail } from "./RunDetail";
import { Transcript } from "./Transcript";

/** Why the named orchestrator cannot be conversed with, or null when it can. */
function whyUnusable(named: string | null, agent: AgentView | undefined): string | null {
  if (named === null) {
    return "The policy in force names no agent to converse with.";
  }
  if (!agent) {
    return `The policy in force names ${named} to converse with, but it is not available.`;
  }
  if (agent.groundingMode !== "delegation") {
    return `The policy in force names ${named} to converse with, but it does not delegate to other agents.`;
  }
  if (agent.gate.kind === "not-permitted" || agent.gate.kind === "mismatch") {
    return `The policy in force does not permit ${named} to run here.`;
  }
  return null;
}

export function ConversationHome({ directory }: { directory: Directory }) {
  const api = useConversationApi();
  const flowApi = useFlowApi();
  const named = directory.orchestratorId;
  const orchestrator = directory.agents.find((a) => a.id === named);
  const unusable = whyUnusable(named, orchestrator);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [past, setPast] = useState<ConversationSummary[]>([]);
  const [text, setText] = useState("");
  const [attached, setAttached] = useState<AttachedInventory | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ message: string; inventory: AttachedInventory | null } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [flow, setFlow] = useState<FlowLoad>({ state: "loading" });
  const runId = new URLSearchParams(useLocation().split("?")[1]).get("run");
  const box = useRef<HTMLTextAreaElement>(null);

  const reloadPast = useCallback(
    (signal?: AbortSignal) => api.list(signal).then(setPast, () => undefined),
    [api],
  );

  useEffect(() => {
    const abort = new AbortController();
    void reloadPast(abort.signal);
    return () => abort.abort();
  }, [reloadPast]);

  // The phases do not depend on the conversation: if they fail, only the tracker says so.
  useEffect(() => {
    const abort = new AbortController();
    flowApi.get(abort.signal).then(
      (loaded) => setFlow({ state: "loaded", flow: loaded }),
      (e: unknown) => abort.signal.aborted || setFlow({ state: "failed", message: errorMessage(e) }),
    );
    return () => abort.abort();
  }, [flowApi]);

  const frame = {
    phases: <PhaseTracker load={flow} />,
  };

  if (unusable || !orchestrator) {
    return (
      <Workspace
        {...frame}
        title="No conversation is available"
        centre={
          <>
            <p>{unusable} You can still use each agent on its own.</p>
            <p>
              <Link to="/agents">Open the agent directory</Link>
            </p>
          </>
        }
        context={<ContextPanel />}
      />
    );
  }

  /** Reads `text` as an inventory and attaches it, or says why it cannot. */
  function attach(content: string, name: string | null): boolean {
    try {
      setAttached(readInventory(content, name));
      setAttachError(null);
      setAnnouncement("Inventory attached.");
      return true;
    } catch (e) {
      setAttachError(e instanceof NotAnInventory ? e.message : errorMessage(e));
      return false;
    }
  }

  async function attachFile(file: File | undefined) {
    if (!file) return;
    try {
      attach(await file.text(), file.name);
    } catch (e) {
      setAttachError(`Data Director could not read ${file.name}: ${errorMessage(e)}`);
    }
  }

  function removeInventory() {
    setAttached(null);
    setAnnouncement("Inventory removed.");
    box.current?.focus();
  }

  // A whole inventory pasted into the box becomes a chip, not text (#443).
  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = event.clipboardData.getData("text");
    if (!looksLikeInventory(pasted)) return;
    event.preventDefault();
    attach(pasted, null);
  }

  function onDragOver(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(true);
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(false);
    void attachFile(event.dataTransfer.files[0]);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await deliver(text.trim(), attached, null);
  }

  /** Sends the answer to the latest turn's choice question, said in words as `message`. What is
   * in the message box stays there. */
  async function answerQuestion(answer: ChoiceAnswer, message: string) {
    await deliver(message, null, answer);
  }

  async function deliver(
    message: string,
    inventory: AttachedInventory | null,
    answer: ChoiceAnswer | null,
  ) {
    if (!orchestrator || (!message && !inventory) || busy) return;
    // A typed message comes from the box, and goes back to it if the send fails.
    const fromBox = answer === null;
    setBusy(true);
    setError(null);
    setAttachError(null);
    setAnnouncement("Waiting for a reply.");
    // The message and its inventory move into the transcript while the reply is awaited, and
    // come back to the box if the send fails, so nothing typed or attached is lost.
    setSent({ message, inventory });
    if (fromBox) {
      setText("");
      setAttached(null);
    }
    let id = conversationId;
    let stored = false;
    // The latest turn this page shows: the server refuses the turn if the conversation has
    // moved on since, so a message sent again after a dropped connection never runs twice.
    const follows = conversation?.turns[conversation.turns.length - 1]?.invocation_id ?? null;
    try {
      id ??= await api.create();
      setConversationId(id);
      const document = inventory?.document ?? null;
      await (answer
        ? api.sendTurn(id, orchestrator.id, message, follows, document, undefined, answer)
        : api.sendTurn(id, orchestrator.id, message, follows, document));
      // The turn is stored: from here a failure is in showing the reply, not in sending it, so
      // the message must not come back to the box to be sent twice (#337).
      stored = true;
      // Once more if the first read gets no response: the reply is there to be read.
      const sentTo = id;
      const updated = await api.get(sentTo).catch((e: unknown) => {
        if (e instanceof Unreachable) return api.get(sentTo);
        throw e;
      });
      setConversation(updated);
      const last = updated.turns[updated.turns.length - 1];
      const asks = last ? replyQuestion(last.envelope) : null;
      setAnnouncement(
        last
          ? `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.` +
              (asks ? ` It asks you to choose: ${asks.question_prompt}` : "")
          : "",
      );
      void reloadPast();
    } catch (e) {
      if (stored) {
        void reloadPast();
        setError(
          "Your message was sent and answered, but Data Director could not show the reply " +
            `(${errorMessage(e)}). Open this conversation from Conversations to see it.`,
        );
        setAnnouncement("");
        return;
      }
      if (fromBox) {
        setText(message);
        setAttached(inventory);
      }
      if (e instanceof Unreachable) {
        // The server may have received the turn and be running it, so show what it stored.
        if (id) api.get(id).then(setConversation, () => undefined);
        setError(
          "Data Director could not reach the server, so this message may not have been sent. " +
            "Your message is kept: sending it again is safe, because a message that was " +
            "received is not run twice.",
        );
      } else if (e instanceof TurnConflict) {
        if (id) api.get(id).then(setConversation, () => undefined);
        setError(
          "This conversation has changed since you wrote this: another message was answered or " +
            "is still being answered. Your message is kept. Check the conversation above, then " +
            "send it again if it is still needed.",
        );
      } else {
        setError(
          e instanceof RunRefused
            ? `${e.problem.title}: ${e.message}`
            : `Data Director could not send this: ${errorMessage(e)}`,
        );
      }
      setAnnouncement("");
    } finally {
      setSent(null);
      setBusy(false);
      box.current?.focus();
    }
  }

  function reset() {
    setConversationId(null);
    setConversation(null);
    setError(null);
    setText("");
    setAttached(null);
    setAttachError(null);
    setAnnouncement("");
    box.current?.focus();
  }

  async function reopen(id: string) {
    try {
      setConversation(await api.get(id));
      setConversationId(id);
      setError(null);
      box.current?.focus();
    } catch (e) {
      setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
    }
  }

  // Opening a run shows it in its card and closing it hides it; focus stays on the card's button.
  function toggleRun(envelope: Envelope) {
    navigate(envelope.invocation_id === runId ? "/" : `/?run=${encodeURIComponent(envelope.invocation_id)}`);
  }

  // A run named in the address but not in the transcript, as after a reload (the conversation is
  // not in the address), is shown above the message box so the link still opens it.
  const inTranscript = conversation?.turns
    .flatMap((t) => t.children)
    .some((c) => c.invocation_id === runId);

  return (
    <Workspace
      {...frame}
      title="Talk to Data Director"
      titleHidden
      centre={
        <section aria-labelledby="conversation-heading" className="conversation-main">
          <h2 id="conversation-heading" className="visually-hidden">
            Conversation
          </h2>
          {((conversation && conversation.turns.length > 0) || sent !== null) && (
            <Transcript
              conversation={conversation}
              agents={directory.agents}
              onToggleRun={toggleRun}
              selectedRun={runId}
              pending={
                sent === null
                  ? null
                  : { agentId: orchestrator.id, message: sent.message, inventory: sent.inventory }
              }
              onAnswer={(answer, message) => void answerQuestion(answer, message)}
            />
          )}
          {runId && !inTranscript && (
            <section aria-labelledby="linked-run" className="callout">
              <h3 id="linked-run">
                Run <code>{runId}</code>
              </h3>
              <RunDetail invocationId={runId} agents={directory.agents} idPrefix="linked-run" />
              <p>
                <Button icon={X} onPress={() => navigate("/")}>Close the run</Button>
              </p>
            </section>
          )}
          {/* Dropping a file is a shortcut for the Attach inventory button, which keyboard and
              screen reader users have, so the form's drag listeners need no role of their own. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
          <form
            onSubmit={(e) => void send(e)}
            aria-busy={busy}
            className={dropping ? "dropping" : undefined}
            onDragOver={onDragOver}
            onDragLeave={() => setDropping(false)}
            onDrop={onDrop}
          >
            <div className="field">
              <label htmlFor="message">What would you like to do?</label>
              <textarea
                id="message"
                ref={box}
                rows={3}
                aria-describedby="message-hint"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onPaste={onPaste}
                onKeyDown={(e) => {
                  // Ctrl+Enter (Cmd+Enter on a Mac) sends; the Send button's rules still apply.
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (!busy && (text.trim() || attached)) e.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <p id="message-hint" className="hint">
                Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on a Mac)
                to send.
              </p>
            </div>
            <div className="composer-attach">
              {attached ? (
                <InventoryChip
                  fileCount={attached.fileCount}
                  madeAt={attached.madeAt}
                  name={attached.name}
                  source={{ document: attached.document }}
                  onRemove={removeInventory}
                />
              ) : (
                <FileTrigger
                  acceptedFileTypes={["application/json", ".json"]}
                  onSelect={(files) => void attachFile(files?.[0])}
                >
                  <Button icon={Paperclip} isDisabled={busy}>Attach inventory</Button>
                </FileTrigger>
              )}
              <a href={INVENTORY_GUIDE}>How do I make an inventory?</a>
            </div>
            {attachError && (
              <p role="alert" className="callout status-danger">
                {attachError}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              icon={SendHorizontal}
              isDisabled={!busy && !text.trim() && !attached}
              isPending={busy}
            >
              {busy ? "Sending…" : "Send"}
            </Button>
          </form>
          <div role="status" aria-live="polite" className="visually-hidden">
            {announcement}
          </div>
          {error && (
            <div role="alert" className="callout status-danger">
              <p>{error}</p>
            </div>
          )}
        </section>
      }
      history={
        <EarlierConversations
          conversations={past}
          currentId={conversationId}
          onOpen={(id) => void reopen(id)}
          onNew={reset}
        />
      }
      context={<ContextPanel conversation={conversation} />}
    />
  );
}
