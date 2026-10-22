/**
 * The transcript: an ordered list of turns. Each reply is labelled `agent_id@agent_version`,
 * a change of version since an earlier turn is marked (ADR-0012 §12), and each delegated child
 * is a card that opens its run. Abstained, referred and failed replies use the run view's
 * outcome wording, not a generic error.
 */

import type { Conversation, ConversationTurn } from "../../conversation/types";
import { Link } from "../../route";
import { OUTCOME, REASON } from "../../manifest/wording";
import type { Envelope } from "../../run/types";

function replyText(conversation: Conversation, turn: ConversationTurn): string {
  const entry = conversation.history.find(
    (h) => h.role === "agent" && h.turn_invocation_id === turn.invocation_id,
  );
  return entry?.turn_text ?? turn.envelope.outcome.statement;
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

function ChildCard({
  child,
  onOpen,
  selected,
}: {
  child: Envelope;
  onOpen: (child: Envelope) => void;
  selected: boolean;
}) {
  const { label, tone } = OUTCOME[child.outcome.status];
  // TODO: a suspended run is the only sign of review waiting until the gate exists (#72, #73).
  const waiting = child.outcome.status === "suspended";
  const name = `${child.agent_id}@${child.agent_version}`;
  return (
    <li className="callout" {...(selected ? { "aria-current": "true" as const } : {})}>
      <p>
        <code>{name}</code> <span className={`status status-${tone}`}>{label}</span>
        {waiting && (
          <>
            {" "}
            <span className="status status-warn">⏸ Waiting for review</span>
          </>
        )}
      </p>
      <button type="button" onClick={() => onOpen(child)}>
        Open run<span className="visually-hidden"> of {name}</span>
      </button>{" "}
      <Link to={`/agents?agent=${encodeURIComponent(child.agent_id)}`}>
        About this agent<span className="visually-hidden"> {child.agent_id}</span>
      </Link>
    </li>
  );
}

export function Transcript({
  conversation,
  onOpenRun,
  selectedRun = null,
}: {
  conversation: Conversation;
  onOpenRun: (child: Envelope) => void;
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
            </strong>{" "}
            {replyText(conversation, turn)}
          </p>
          <OutcomeNote envelope={turn.envelope} />
          {turn.children.length > 0 && (
            <ul aria-label={`Agents ${turn.agent_id} delegated to`} className="plain-list">
              {turn.children.map((child) => (
                <ChildCard
                  key={child.invocation_id}
                  child={child}
                  onOpen={onOpenRun}
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
