/**
 * What the conversation endpoints return (app/src/dd_app/app.py, harness conversations.py), as
 * the shell reads it. A field it does not know is ignored, not refused.
 */

import type { Envelope } from "../run/types";
import type { InventorySummary, ProjectInventory } from "./inventory";
import type { ChoiceAnswer } from "./question";

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
    { message_text?: string; project_inventory?: InventorySummary; choice_answer?: ChoiceAnswer }
  >;
  version_changes: VersionChange[];
  history: HistoryEntry[];
}
