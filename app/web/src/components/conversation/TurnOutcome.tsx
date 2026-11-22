/**
 * How a turn that did not succeed ends in the transcript: the outcome's wording, and for a turn
 * that failed, plain words in place of the agent's text, that text behind a disclosure for
 * operators, and **Try again** on the latest turn (docs/specs/app.md). A turn referred or abstained
 * is offered to a data steward (`RunStewardOffer`).
 */

import type { Conversation, ConversationTurn } from "../../conversation/types";
import { OUTCOME, REASON } from "../../manifest/wording";
import type { Envelope } from "../../run/types";
import { RunStewardOffer } from "../escalation/StewardOffer";
import { Button } from "../ui/Button";

/** What a reply that failed says in place of the agent's own text, which is for operators. */
export const FAILED_REPLY =
  "Data Director could not answer this message. Nothing was changed, and anything the message " +
  "attached is kept in the project. Try again in a moment; if it keeps failing, tell whoever " +
  "runs Data Director for you.";

export function OutcomeNote({ envelope }: { envelope: Envelope }) {
  const { status, reason_code: code } = envelope.outcome;
  if (status === "succeeded") return null;
  if (status === "failed" && !code) {
    return (
      <details className="muted">
        <summary>Details for whoever runs Data Director</summary>
        <p>
          <code>{envelope.outcome.statement}</code>
        </p>
      </details>
    );
  }
  const reason = code ? REASON[code] : undefined;
  return (
    <>
      <p className="muted">
        {OUTCOME[status].label}.{" "}
        {reason ? `${reason.meaning} ${reason.next}` : envelope.outcome.statement}
      </p>
      <RunStewardOffer envelope={envelope} />
    </>
  );
}

/** Sends the latest turn's message again if that turn failed; nothing for any other turn. */
export function RetryTurn({
  conversation,
  turn,
  latest,
  disabled,
  onRetry,
}: {
  conversation: Conversation;
  turn: ConversationTurn;
  latest: boolean;
  disabled: boolean;
  onRetry: ((message: string) => void) | undefined;
}) {
  if (!latest || !onRetry || turn.envelope.outcome.status !== "failed") return null;
  const message = conversation.inputs[turn.invocation_id]?.message_text ?? "";
  return (
    <p>
      <Button isDisabled={disabled} onPress={() => onRetry(message)}>
        Try again
      </Button>
    </p>
  );
}
