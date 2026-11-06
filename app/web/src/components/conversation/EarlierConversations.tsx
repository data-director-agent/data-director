/**
 * The conversations a person can reopen, each named by its title (docs/specs/app.md). The harness
 * derives the title: a model's from the first turn, or the start of the first message
 * (docs/specs/orchestration.md); the shell writes none. Beneath it, smaller, are when the
 * conversation started and how many turns it has. Both stay in the button's accessible name, so two
 * conversations with the same title can still be told apart.
 */

import { FolderOpen } from "lucide-react";
import type { ConversationSummary } from "../../conversation/types";
import { Button } from "../ui/Button";

import "./EarlierConversations.css";

function started(at: string): string {
  const date = new Date(at);
  return Number.isNaN(date.getTime())
    ? at
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function EarlierConversations({
  conversations,
  onOpen,
}: {
  conversations: ConversationSummary[];
  onOpen: (conversationId: string) => void;
}) {
  if (conversations.length === 0) return null;
  return (
    <section aria-labelledby="past-heading">
      <h3 id="past-heading">Earlier conversations</h3>
      <ul className="plain-list">
        {conversations.map((c) => (
          <li key={c.conversation_id}>
            <Button
              variant="quiet"
              icon={FolderOpen}
              className="earlier-conversation"
              onPress={() => onOpen(c.conversation_id)}
            >
              <span className="earlier-conversation-text">
                <span className="earlier-conversation-title">{c.title}</span>{" "}
                <span className="earlier-conversation-meta">
                  <time dateTime={c.started_at}>{started(c.started_at)}</time>,{" "}
                  {c.turns} {c.turns === 1 ? "turn" : "turns"}
                </span>
              </span>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
