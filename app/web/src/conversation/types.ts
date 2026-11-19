/**
 * What the conversation endpoints return (app/src/dd_app/app.py, harness conversations.py), as
 * the shell reads it. A field it does not know is ignored, not refused.
 */

import type { Envelope } from "../run/types";
import type { DocumentationSummary } from "./documentation";
import type { InventorySummary, ProjectInventory } from "./inventory";
import type { ReplyAnswers } from "./question";

export interface ConversationSummary {
  conversation_id: string;
  /** The project the conversation was started in, if the app keeps projects. */
  project_id?: string | null;
  agent_id: string;
  /** A model's title from the first turn, or else the start of the first message. */
  title: string;
  title_source: "model" | "message";
  turns: number;
  started_at: string;
  last_completed_at?: string;
  last_status?: string;
}

/** A deleted conversation its starter or the project's owner may still restore
 * (`GET /api/conversations/deleted`, docs/specs/projects.md, invariants 29 to 31). */
export interface DeletedConversation {
  conversation_id: string;
  project_id: string;
  /** Its title as the harness derives it, or null if it had no turn. */
  title: string | null;
  /** When it was deleted, and by whom. */
  at: string;
  by: { principal_id: string; name?: string };
  restorable_until: string;
}

export interface ConversationTurn {
  turn_index: number;
  invocation_id: string;
  agent_id: string;
  agent_version: string;
  status: string;
  completed_at: string;
  envelope: Envelope;
  children: Envelope[];
}

export interface VersionChange {
  turn_index: number;
  agent_id: string;
  from: string;
  to: string;
}

export interface HistoryEntry {
  role: "user" | "agent";
  turn_text: string;
  turn_agent_id?: string;
  turn_agent_version?: string;
  turn_invocation_id?: string;
}

export interface Conversation {
  conversation_id: string;
  /** The project the conversation was started in, where the server keeps projects. */
  project_id?: string | null;
  /** The inventory the project holds now. */
  inventory?: ProjectInventory | null;
  turns: ConversationTurn[];
  inputs: Record<
    string,
    {
      message_text?: string;
      project_inventory?: InventorySummary;
      project_documentation?: DocumentationSummary[];
      reply_answers?: ReplyAnswers;
    }
  >;
  version_changes: VersionChange[];
  history: HistoryEntry[];
}
