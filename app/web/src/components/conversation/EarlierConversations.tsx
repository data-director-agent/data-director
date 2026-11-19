/**
 * The person's conversations, beside the open one (docs/specs/app.md): a button to start a new
 * conversation, then each conversation they can reopen, named by its title, newest first as the
 * server lists them. The harness derives the title: a model's from the first turn, or the start
 * of the first message (docs/specs/orchestration.md); the shell writes none. Beneath it, smaller,
 * are when the conversation started and how many turns it has. Both stay in the button's
 * accessible name, so two conversations with the same title can still be told apart. The open
 * conversation is marked as current. With `onDeleted`, each has a button beside it that deletes
 * it after asking (`DeleteConversation`).
 */

import { MessageSquare, MessageSquarePlus } from "lucide-react";
import type { ConversationSummary } from "../../conversation/types";
import { Button } from "../ui/Button";
import { DeleteConversation } from "./DeleteConversation";

import "./EarlierConversations.css";
import { formatDateTime } from "../../format";

function started(at: string): string {
  return formatDateTime(at, { dateStyle: "medium", timeStyle: "short" });
}

export function EarlierConversations({
  conversations,
  currentId = null,
  onOpen,
  onNew,
  onDeleted,
  restoreDays,
}: {
  conversations: ConversationSummary[];
  currentId?: string | null;
  onOpen: (conversationId: string) => void;
  onNew?: () => void;
  /** Called once a conversation is deleted; without it, none can be deleted from here. */
  onDeleted?: (conversationId: string) => void;
  /** For how many days a deleted conversation may be restored, if known. */
  restoreDays?: number | undefined;
}) {
  return (
    <section aria-labelledby="past-heading" className="workspace-history">
      <h2 id="past-heading">Conversations</h2>
      {onNew && (
        <p>
          <Button icon={MessageSquarePlus} onPress={onNew}>
            New conversation
          </Button>
        </p>
      )}
      {conversations.length === 0 ? (
        <p className="muted">No conversations yet.</p>
      ) : (
        <ul className="plain-list">
          {conversations.map((c) => {
            const current = c.conversation_id === currentId;
            return (
              <li key={c.conversation_id} className="earlier-conversation-row">
                <Button
                  variant="quiet"
                  icon={MessageSquare}
                  className="earlier-conversation"
                  onPress={() => onOpen(c.conversation_id)}
                  {...(current ? { "aria-current": "true" as const } : {})}
                >
                  <span className="earlier-conversation-text">
                    <span className="earlier-conversation-title">{c.title}</span>{" "}
                    <span className="earlier-conversation-meta">
                      <time dateTime={c.started_at}>{started(c.started_at)}</time>,{" "}
                      {c.turns} {c.turns === 1 ? "turn" : "turns"}
                    </span>
                  </span>
                </Button>
                {onDeleted && (
                  <DeleteConversation
                    conversationId={c.conversation_id}
                    title={c.title}
                    restoreDays={restoreDays}
                    onDeleted={onDeleted}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
