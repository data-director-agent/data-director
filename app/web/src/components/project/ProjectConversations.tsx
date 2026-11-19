/**
 * The project's conversations, in the project page's side bar beneath its documents
 * (docs/specs/app.md): a link to start a new conversation in the project, then each of its
 * conversations, newest first as the server lists them, named by its title with when it started
 * and how many turns it has beneath. Each is a link to the conversation, so it can be opened in a
 * new tab and left with Back. The project page makes its project the active one, so a
 * conversation opened or started from here is in this project.
 *
 * Beneath them are the project's recently deleted conversations, which may be restored from here
 * (`DeletedConversations`); restoring one reads the list again.
 *
 * The list is a convenience: while it is read, or if it cannot be, it says so in a line and the
 * documents beside it are unaffected.
 */

import { MessageSquare, MessageSquarePlus } from "lucide-react";
import { useEffect, useState } from "react";

import { useConversationApi } from "../../conversation/api";
import type { ConversationSummary } from "../../conversation/types";
import { Link, homePath } from "../../route";
import { formatDateTime } from "../../format";
import { DeletedConversations } from "./DeletedConversations";

type Load =
  | { state: "loading" }
  | { state: "failed" }
  | { state: "loaded"; value: ConversationSummary[] };

function started(at: string): string {
  return formatDateTime(at, { dateStyle: "medium", timeStyle: "short" });
}

export function ProjectConversations({ projectId }: { projectId: string }) {
  const api = useConversationApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [restored, setRestored] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api.list(controller.signal).then(
      (all) =>
        setLoad({
          state: "loaded",
          value: all.filter((c) => (c.project_id ?? null) === projectId),
        }),
      () => {
        if (!controller.signal.aborted) setLoad({ state: "failed" });
      },
    );
    return () => controller.abort();
  }, [api, projectId, restored]);

  const list = () => {
    if (load.state === "loading") {
      return (
        <p role="status" className="muted">
          Reading the conversations…
        </p>
      );
    }
    if (load.state === "failed") {
      return (
        <p role="alert" className="callout status-danger">
          The conversations could not be read.
        </p>
      );
    }
    if (load.value.length === 0) return <p className="muted">No conversations yet.</p>;
    return (
      <ul className="plain-list">
        {load.value.map((c) => (
          <li key={c.conversation_id}>
            <Link to={homePath({ conversation: c.conversation_id })} className="document-entry">
              <MessageSquare className="document-entry-icon" size="1.125em" aria-hidden="true" />
              <span className="document-entry-name">{c.title}</span>
              <span className="document-entry-detail">
                <time dateTime={c.started_at}>{started(c.started_at)}</time>, {c.turns}{" "}
                {c.turns === 1 ? "turn" : "turns"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <nav className="project-conversations" aria-labelledby="project-conversations-heading">
      <h2 id="project-conversations-heading" className="document-group-heading">
        Conversations
        {load.state === "loaded" && (
          <>
            {" "}
            <span className="document-group-count">({load.value.length})</span>
          </>
        )}
      </h2>
      <ul className="plain-list">
        <li>
          <Link to={homePath({})} className="document-entry">
            <MessageSquarePlus className="document-entry-icon" size="1.125em" aria-hidden="true" />
            <span className="document-entry-name">New conversation</span>
          </Link>
        </li>
      </ul>
      {list()}
      <DeletedConversations projectId={projectId} onRestored={() => setRestored((n) => n + 1)} />
    </nav>
  );
}
