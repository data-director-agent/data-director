/**
 * The transcript: an ordered list of turns. Each reply is labelled `agent_id@agent_version`,
 * a change of version since an earlier turn is marked (ADR-0012 §12), and each delegated child
 * is a card that opens its run, with its evidence, in place. Abstained, referred and failed
 * replies use the run view's outcome wording, not a generic error.
 */

import "./Transcript.css";

import Markdown from "react-markdown";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { Conversation, ConversationTurn } from "../../conversation/types";
import type { AgentView } from "../../manifest/normalise";
import { Link } from "../../route";
import { OUTCOME, REASON } from "../../manifest/wording";
import type { Envelope } from "../../run/types";
import { ModelTag } from "../capabilities/ModelDisclosure";
import { Button } from "../ui/Button";
import { RunDetail } from "./RunDetail";

function replyText(conversation: Conversation, turn: ConversationTurn): string {
  const entry = conversation.history.find(
    (h) => h.role === "agent" && h.turn_invocation_id === turn.invocation_id,
  );
  return entry?.turn_text ?? turn.envelope.outcome.statement;
}

/** What powers the agent, beside its name; nothing when it is not in the directory. */
function ModelOf({ agents, agentId }: { agents: AgentView[]; agentId: string }) {
  const agent = agents.find((a) => a.id === agentId);
  if (!agent) return null;
  return (
    <>
      {" "}
      <ModelTag agent={agent} />
    </>
  );
}

function OutcomeNote({ envelope }: { envelope: Envelope }) {
  const { status, reason_code: code } = envelope.outcome;
  if (status === "succeeded") return null;
  const reason = code ? REASON[code] : undefined;
  return (
    <p className="muted">
      {OUTCOME[status].label}.{" "}
      {reason ? `${reason.meaning} ${reason.next}` : envelope.outcome.statement}
    </p>
  );
}

/**
 * A delegated child as a disclosure: its button shows or hides the run inside the card, and
 * focus stays on the button. Which run is open is the `run` query parameter, so only one is
 * open at a time and Back and reload keep it.
 */
function ChildCard({
  child,
  agents,
  onToggle,
  selected,
}: {
  child: Envelope;
  agents: AgentView[];
  onToggle: (child: Envelope) => void;
  selected: boolean;
}) {
  const { label, tone } = OUTCOME[child.outcome.status];
  // TODO(#72, #73): a suspended run is the only sign of review waiting until the gate exists.
  const waiting = child.outcome.status === "suspended";
  const name = `${child.agent_id}@${child.agent_version}`;
  const regionId = `run-${child.invocation_id}`;
  return (
    <li className="callout child-card" {...(selected ? { "aria-current": "true" as const } : {})}>
      <p>
        <code>{name}</code> <span className={`status status-${tone}`}>{label}</span>
        <ModelOf agents={agents} agentId={child.agent_id} />
        {waiting && (
          <>
            {" "}
            <span className="status status-warn">⏸ Waiting for review</span>
          </>
        )}
      </p>
      <Button
        size="small"
        icon={selected ? ChevronUp : ChevronDown}
        aria-expanded={selected}
        aria-controls={regionId}
        onPress={() => onToggle(child)}
      >
        {selected ? "Hide the run" : "Show the run"}
        <span className="visually-hidden"> of {name}</span>
      </Button>{" "}
      <Link to={`/agents?agent=${encodeURIComponent(child.agent_id)}`}>
        About this agent<span className="visually-hidden"> {child.agent_id}</span>
      </Link>
      <div id={regionId} className="child-run" hidden={!selected}>
        {selected && <RunDetail invocationId={child.invocation_id} agents={agents} idPrefix={regionId} />}
      </div>
    </li>
  );
}

export function Transcript({
  conversation,
  agents,
  onToggleRun,
  selectedRun = null,
}: {
  conversation: Conversation;
  agents: AgentView[];
  onToggleRun: (child: Envelope) => void;
  selectedRun?: string | null;
}) {
  return (
    <ol className="transcript" aria-label="Conversation">
      {conversation.turns.map((turn) => (
        <li key={turn.invocation_id}>
          {conversation.version_changes
            .filter((c) => c.turn_index === turn.turn_index)
            .map((c) => (
              <p key={`${c.agent_id}-${c.to}`} className="callout status-warn">
                <code>{c.agent_id}</code> changed version from <code>{c.from}</code> to{" "}
                <code>{c.to}</code> since an earlier turn.
              </p>
            ))}
          <p>
            <strong>You:</strong> {conversation.inputs[turn.invocation_id]?.message_text}
          </p>
          <p>
            <strong>
              <code>
                {turn.agent_id}@{turn.agent_version}
              </code>
              :
            </strong>
            <ModelOf agents={agents} agentId={turn.agent_id} />
          </p>
          <div className="markdown">
            <Markdown>{replyText(conversation, turn)}</Markdown>
          </div>
          <OutcomeNote envelope={turn.envelope} />
          {turn.children.length > 0 && (
            <ul aria-label={`Agents ${turn.agent_id} delegated to`} className="plain-list">
              {turn.children.map((child) => (
                <ChildCard
                  key={child.invocation_id}
                  child={child}
                  agents={agents}
                  onToggle={onToggleRun}
                  selected={child.invocation_id === selectedRun}
                />
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
