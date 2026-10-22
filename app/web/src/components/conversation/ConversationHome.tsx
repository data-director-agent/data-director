/**
 * The home page: a conversation with the orchestrator (ADR-0024 §9-17).
 *
 * The orchestrator is the agent the profile names (ADR-0024 §10), never one the shell picks.
 * When the profile names none, the named agent is not running, its card does not declare
 * `delegation` grounding, or the policy does not permit it, the page says which and links to the
 * directory (§12). The server builds each turn's history; the page sends the agent and the message.
 * Until there is authentication (#17) the conversation acts for the operator (ADR-0018).
 *
 * A new reply is announced in a polite live region, the busy state is announced, and focus
 * returns to the message box.
 */

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useConversationApi } from "../../conversation/api";
import type { Conversation, ConversationSummary } from "../../conversation/types";
import type { AgentView, Directory } from "../../manifest/normalise";
import { Link, navigate, useLocation } from "../../route";
import { OUTCOME } from "../../manifest/wording";
import { RunRefused, errorMessage } from "../../run/api";
import type { Envelope } from "../../run/types";
import { RunPanel } from "./RunPanel";
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
    const named = directory.orchestratorId;
  const orchestrator = directory.agents.find((a) => a.id === named);
  const unusable = whyUnusable(named, orchestrator);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [past, setPast] = useState<ConversationSummary[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const runId = new URLSearchParams(useLocation().split("?")[1]).get("run");
  const returnFocus = useRef<HTMLElement | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const openHeading = useRef<HTMLHeadingElement>(null);

  const reloadPast = useCallback(
    (signal?: AbortSignal) => api.list(signal).then(setPast, () => undefined),
    [api],
  );

  useEffect(() => {
    const abort = new AbortController();
    void reloadPast(abort.signal);
    return () => abort.abort();
  }, [reloadPast]);

  useEffect(() => {
    if (runId) openHeading.current?.focus();
  }, [runId]);

  if (unusable || !orchestrator) {
    return (
      <section aria-labelledby="no-orchestrator">
        <h1 id="no-orchestrator">No conversation is available</h1>
        <p>
          {unusable} You can still use each agent on its own.
        </p>
        <p>
<Link to="/agents">Open the agent directory</Link>
        </p>
      </section>
    );
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!orchestrator || !message || busy) return;
    setBusy(true);
    setError(null);
    setAnnouncement("Waiting for a reply.");
    try {
      const id = conversationId ?? (await api.create());
      setConversationId(id);
      await api.sendTurn(id, orchestrator.id, message);
      const updated = await api.get(id);
      setConversation(updated);
      setText("");
      const last = updated.turns[updated.turns.length - 1];
      setAnnouncement(
        last
          ? `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.`
          : "",
      );
      void reloadPast();
    } catch (e) {
      setError(
        e instanceof RunRefused
          ? `${e.problem.title}: ${e.message}`
          : `Data Director could not send this: ${errorMessage(e)}`,
      );
      setAnnouncement("");
    } finally {
      setBusy(false);
      box.current?.focus();
    }
  }

  function reset() {
    setConversationId(null);
    setConversation(null);
    setError(null);
    setText("");
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

  function openRun(envelope: Envelope) {
    returnFocus.current = document.activeElement as HTMLElement | null;
    navigate(`/?run=${encodeURIComponent(envelope.invocation_id)}`);
  }

  function closeRun() {
    navigate("/");
    queueMicrotask(() => (returnFocus.current ?? box.current)?.focus());
  }

  const selected = conversation?.turns
    .flatMap((t) => t.children)
    .find((c) => c.invocation_id === runId);

  return (
    <div className={`conversation-layout${runId ? " has-run" : ""}`}>
    <section aria-labelledby="conversation-heading" className="conversation-main">
      <h1 id="conversation-heading">Talk to Data Director</h1>
      <p className="muted">
        This conversation acts for {directory.actingFor.name}, as asserted by the operator and not
        authenticated.
      </p>
      <p>
        <button type="button" onClick={reset}>
          New conversation
        </button>{" "}
        <Link to="/agents">Agent directory</Link>
      </p>
      {conversation && conversation.turns.length > 0 && (
        <Transcript conversation={conversation} onOpenRun={openRun} selectedRun={runId} />
      )}
      <form onSubmit={(e) => void send(e)} aria-busy={busy}>
        <div className="field">
          <label htmlFor="message">What would you like to do?</label>
          <textarea
            id="message"
            ref={box}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <button type="submit" disabled={busy || !text.trim()}>
          {busy ? "Sending…" : "Send"}
        </button>
      </form>
      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
      {past.length > 0 && (
        <section aria-labelledby="past-heading">
          <h2 id="past-heading">Earlier conversations</h2>
          <ul className="plain-list">
            {past.map((c) => (
              <li key={c.conversation_id}>
                <button type="button" onClick={() => void reopen(c.conversation_id)}>
                  {c.started_at} ({c.turns} {c.turns === 1 ? "turn" : "turns"})
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
    {runId && (
      <RunPanel
        ref={openHeading}
        invocationId={runId}
        agent={directory.agents.find((a) => a.id === selected?.agent_id)}
        name={selected ? `${selected.agent_id}@${selected.agent_version}` : runId}
        onClose={closeRun}
      />
    )}
    </div>
  );
}
