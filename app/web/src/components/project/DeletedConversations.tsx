/**
 * The project's recently deleted conversations, beneath its conversations on the project's page
 * (docs/specs/app.md, rule 30): each that the person may still restore, with when it was deleted
 * and until when it may be restored, and **Restore**. Nothing is shown while there is none, or
 * if they cannot be read, since the conversations above are what the side bar is for.
 */

import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { useConversationApi } from "../../conversation/api";
import type { DeletedConversation } from "../../conversation/types";
import { formatDateTime } from "../../format";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";

function day(at: string): string {
  return formatDateTime(at, { dateStyle: "medium" });
}

export function DeletedConversations({
  projectId,
  onRestored,
}: {
  projectId: string;
  onRestored: (conversationId: string) => void;
}) {
  const api = useConversationApi();
  const [deleted, setDeleted] = useState<DeletedConversation[]>([]);
  const [tick, setTick] = useState(0);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.deleted(controller.signal).then(
      (all) => setDeleted(all.filter((c) => c.project_id === projectId)),
      () => {
        if (!controller.signal.aborted) setDeleted([]);
      },
    );
    return () => controller.abort();
  }, [api, projectId, tick]);

  const restore = (conversationId: string) => {
    setRestoring(conversationId);
    setError(null);
    api.restore(conversationId).then(
      () => {
        setRestoring(null);
        setTick((n) => n + 1);
        onRestored(conversationId);
      },
      (e: unknown) => {
        setRestoring(null);
        setError(`Data Director could not restore that conversation: ${errorMessage(e)}`);
      },
    );
  };

  if (deleted.length === 0 && error === null) return null;
  return (
    <section aria-labelledby="deleted-conversations-heading" className="deleted-conversations">
      <h3 id="deleted-conversations-heading" className="document-group-heading">
        Recently deleted
      </h3>
      {error && (
        <p role="alert" className="callout status-danger">
          {error}
        </p>
      )}
      <ul className="plain-list">
        {deleted.map((c) => {
          const title = c.title ?? "Untitled conversation";
          return (
            <li key={c.conversation_id} className="deleted-conversation">
              <span className="document-entry-name">{title}</span>
              <span className="document-entry-detail">
                Deleted <time dateTime={c.at}>{day(c.at)}</time>; can be restored until{" "}
                <time dateTime={c.restorable_until}>{day(c.restorable_until)}</time>
              </span>
              <Button
                size="small"
                icon={RotateCcw}
                aria-label={`Restore conversation: ${title}`}
                isPending={restoring === c.conversation_id}
                onPress={() => restore(c.conversation_id)}
              >
                Restore
              </Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
