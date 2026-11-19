/**
 * What the conversation endpoints return, as generated from the app's response models
 * (`../api/generated/responses.ts`), with each turn's inputs read as the shell reads them.
 */

import type { Conversation as SentConversation } from "../api/generated/responses";
import type { DocumentationSummary } from "./documentation";
import type { InventorySummary } from "./inventory";
import type { ReplyAnswers } from "./question";

export type {
  ConversationSummary,
  ConversationTurn,
  DeletedConversation,
} from "../api/generated/responses";

/**
 * The parts of a stored input that the shell shows: the server sends each input as the run store
 * kept it, which its model leaves open. A field the shell does not know is ignored.
 */
export interface TurnInputs {
  message_text?: string;
  project_inventory?: InventorySummary;
  project_documentation?: DocumentationSummary[];
  reply_answers?: ReplyAnswers;
}

/** A conversation as `GET /api/conversations/{id}` sends it, with its turns' inputs typed. */
export interface Conversation extends Omit<SentConversation, "inputs"> {
  /** Every stored input, the delegated runs' too, by `invocation_id`. */
  inputs: Record<string, TurnInputs | null>;
}
