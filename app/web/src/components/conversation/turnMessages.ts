/**
 * What a conversation turn sends, and what the page says of it: the turn's body, a refusal, and
 * the reply's announcement (`useConversationTurns`).
 */

import { NoAnswer, TurnConflict, turnBody, Unreachable } from "../../conversation/api";
import { type ReplyAnswers, replyQuestions } from "../../conversation/question";
import type { ConversationTurn } from "../../conversation/types";
import { OUTCOME } from "../../manifest/wording";
import { RunRefused, errorMessage } from "../../run/api";
import type { RunState } from "../../run/reduce";
import type { Carried } from "./useAttachments";

/** What the newest turn's reply says, as announced. */
export function replyAnnouncement(last: ConversationTurn | undefined): string {
  if (!last) return "";
  const asks = replyQuestions(last.envelope);
  const said = `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.`;
  if (asks.length === 1) return `${said} It asks: ${asks[0]?.question_prompt}`;
  if (asks.length > 1) return `${said} It asks you ${asks.length} questions, one at a time.`;
  return said;
}

/** Why a turn could not be sent, for one that was not stored. */
export function sendFailure(e: unknown): string {
  if (e instanceof NoAnswer) {
    return (
      `Data Director's server did not answer in time (it answered ${e.status}), so this ` +
      "message may not have been sent, or may still be being answered. Your message is " +
      "kept: check the conversation above, and send it again if no reply appears. " +
      "Sending it again is safe, because a message that was received is not run twice."
    );
  }
  if (e instanceof Unreachable) {
    return (
      "Data Director could not reach the server, so this message may not have been sent. " +
      "Your message is kept: sending it again is safe, because a message that was " +
      "received is not run twice."
    );
  }
  if (e instanceof TurnConflict) {
    return (
      "This conversation has changed since you wrote this: another message was answered or " +
      "is still being answered. Your message is kept. Check the conversation above, then " +
      "send it again if it is still needed."
    );
  }
  return e instanceof RunRefused
    ? `${e.problem.title}: ${e.message}`
    : `Data Director could not send this: ${errorMessage(e)}`;
}

/** A turn's body: the answers and what is attached, each only when there is one. */
export function body(
  agentId: string,
  message: string,
  follows: string | null,
  carried: Carried,
  answer: ReplyAnswers | null,
): Record<string, unknown> {
  const inventory = carried.inventory?.document ?? null;
  return turnBody(agentId, message, follows, inventory, answer, carried.document);
}

/** A turn the server refused once its stream was open, before any run began: nothing was run. */
export function refusedInStream(state: RunState): boolean {
  return state.phase === "error" && state.runId === null;
}

/** Why the server refused a turn in its stream, as an error to raise: `TurnConflict` when the
 * conversation has moved on (`turn-conflict`), so that the page reads it again and keeps what
 * the person typed (#391); otherwise the server's words. */
export function streamRefusal(state: RunState): Error {
  const detail = state.error ?? "the turn was refused";
  if (state.errorCode === TURN_CONFLICT) {
    return new TurnConflict({ type: TURN_CONFLICT, title: "The conversation has moved on", detail });
  }
  return new Error(detail);
}

const TURN_CONFLICT = "turn-conflict";
