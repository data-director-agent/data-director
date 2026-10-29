/**
 * The home page: a conversation with the orchestrator (ADR-0024 §9-17), in the centre of the
 * workspace (§18), with the Blueprint's phases on one side and the project's documents on the
 * other. A delegated run opens inside its card in the transcript (§14).
 *
 * The orchestrator is the agent the profile names (ADR-0024 §10), never one the shell picks.
 * When the profile names none, the named agent is not running, its card does not declare
 * `delegation` grounding, or the policy does not permit it, the page says which and links to the
 * directory (§12). The server builds each turn's history; the page sends the agent and the message.
 * Until there is authentication (#17) the conversation acts for the operator (ADR-0018).
 *
 * While a reply is awaited the message sits in the transcript beside a pulsing sign that the
 * orchestrator is working. A new reply is announced in a polite live region, the busy state is
 * announced, and focus returns to the message box.
 */

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { FolderOpen, MessageSquarePlus, SendHorizontal, X } from "lucide-react";
import { useConversationApi } from "../../conversation/api";
import { useFlowApi } from "../../flow/api";
import type { Conversation, ConversationSummary } from "../../conversation/types";
import type { AgentView, Directory } from "../../manifest/normalise";
import { Link, navigate, useLocation } from "../../route";
import { OUTCOME } from "../../manifest/wording";
import { RunRefused, errorMessage } from "../../run/api";
import type { Envelope } from "../../run/types";
import { ActivityLog } from "../workspace/ActivityLog";
import { ContextPanel } from "../workspace/ContextPanel";
import { type FlowLoad, PhaseTracker } from "../workspace/PhaseTracker";
import { StatusBar } from "../workspace/StatusBar";
import { Workspace } from "../workspace/Workspace";
import { Button } from "../ui/Button";
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
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
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
    status: <StatusBar directory={directory} />,
    phases: <PhaseTracker load={flow} agents={directory.agents} />,
    log: <ActivityLog />,
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
        context={<ContextPanel orchestrator={undefined} />}
      />
    );
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!orchestrator || !message || busy) return;
    setBusy(true);
    setError(null);
    setAnnouncement("Waiting for a reply.");
    // The message moves into the transcript while the reply is awaited, and comes back to the
    // box if the send fails, so nothing typed is lost.
    setSent(message);
    setText("");
    try {
      const id = conversationId ?? (await api.create());
      setConversationId(id);
      await api.sendTurn(id, orchestrator.id, message);
      const updated = await api.get(id);
      setConversation(updated);
      const last = updated.turns[updated.turns.length - 1];
      setAnnouncement(
        last
          ? `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.`
          : "",
      );
      void reloadPast();
    } catch (e) {
      setText(message);
      setError(
        e instanceof RunRefused
          ? `${e.problem.title}: ${e.message}`
          : `Data Director could not send this: ${errorMessage(e)}`,
      );
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
      centre={
        <section aria-labelledby="conversation-heading" className="conversation-main">
          <h2 id="conversation-heading" className="visually-hidden">
            Conversation
          </h2>
          <p>
            <Button icon={MessageSquarePlus} onPress={reset}>New conversation</Button>
          </p>
          {((conversation && conversation.turns.length > 0) || sent !== null) && (
            <Transcript
              conversation={conversation}
              agents={directory.agents}
              onToggleRun={toggleRun}
              selectedRun={runId}
              pending={sent === null ? null : { agentId: orchestrator.id, message: sent }}
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
          <form onSubmit={(e) => void send(e)} aria-busy={busy}>
            <div className="field">
              <label htmlFor="message">What would you like to do?</label>
              <textarea
                id="message"
                ref={box}
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  // Ctrl+Enter (Cmd+Enter on a Mac) sends; the Send button's rules still apply.
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (!busy && text.trim()) e.currentTarget.form?.requestSubmit();
                  }
                }}
              />
            </div>
            <Button type="submit" variant="primary" icon={SendHorizontal} isDisabled={!busy && !text.trim()} isPending={busy}>
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
          {past.length > 0 && (
            <section aria-labelledby="past-heading">
              <h3 id="past-heading">Earlier conversations</h3>
              <ul className="plain-list">
                {past.map((c) => (
                  <li key={c.conversation_id}>
                    <Button variant="quiet" icon={FolderOpen} onPress={() => void reopen(c.conversation_id)}>
                      {c.started_at} ({c.turns} {c.turns === 1 ? "turn" : "turns"})
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </section>
      }
      context={<ContextPanel orchestrator={orchestrator} />}
    />
  );
}
