/**
 * The offers of a data steward in the conversation (docs/ui/steward-escalation-flows.md, flow B):
 * beside a run that was referred or abstained, and in place of the orchestrator's `ask-steward`
 * question. Each one explains, offers and opens the dialog in which the researcher sees what will
 * be shared and confirms it (`AskSteward`). An abstention only offers; a step referred for approval
 * stays stopped whatever is chosen. A run already sent shows where its request is instead.
 */

import { LifeBuoy } from "lucide-react";
import { type Ref, useImperativeHandle, useRef } from "react";

import { type Question, type ReplyAnswers, answersText } from "../../conversation/question";
import { OUTCOME, REASON } from "../../manifest/wording";
import { liveFor } from "../../project/escalations";
import type { Envelope } from "../../run/types";
import { Button } from "../ui/Button";
import { useSteward } from "./StewardContext";
import { statusLine } from "./wording";

/** Moves the focus to the offer, as `QuestionSeries` does to its question. */
interface Focusable {
  focus(): void;
}

/** The orchestrator's offer of a data steward (`dd_agent_orchestrator_model.steward_offer`). */
export const STEWARD_KEY = "ask-steward";
const SEND = "send";
const NOT_NOW = "not-now";

const APPROVAL = "policy_requires_approval";
// A paused project is already with its stewards, so its referral offers no new request.
const ALREADY_WITH_STEWARDS = "project_paused";

/** Whether the questions are the orchestrator's offer of a data steward, alone. */
export function isStewardOffer(questions: readonly Question[]): boolean {
  return questions.length === 1 && questions[0]?.question_key === STEWARD_KEY;
}

/** Offers a data steward for a run that was referred or abstained; nothing for any other run. */
export function RunStewardOffer({ envelope }: { envelope: Envelope }) {
  const steward = useSteward();
  const { status, reason_code: code, statement } = envelope.outcome;
  if (!steward || (status !== "referred" && status !== "abstained") || code === ALREADY_WITH_STEWARDS) return null;
  const live = liveFor(steward.escalations?.escalations ?? [], envelope.invocation_id);
  if (live) {
    return (
      <p className="hint">
        <LifeBuoy size="1em" aria-hidden="true" /> {statusLine(live)}
      </p>
    );
  }
  const mandatory = status === "referred" && code === APPROVAL;
  const reason = code ? REASON[code] : undefined;
  return (
    <p>
      <Button
        size="small"
        icon={LifeBuoy}
        onPress={() =>
          steward.offer({
            origin: { kind: mandatory ? "policy_gate" : "agent", invocation_id: envelope.invocation_id },
            note: reason ? `${OUTCOME[status].label}: ${reason.meaning}` : statement,
            matter: [`The run that was ${status}, and why: ${reason?.meaning ?? statement}`],
            mandatory,
          })
        }
      >
        Ask a data steward
      </Button>
    </p>
  );
}

/**
 * The orchestrator's `ask-steward` question, answered by its two buttons: **Ask a data steward**
 * opens the dialog, and the answer `send` goes once the request is sent; **Not now** answers
 * `not-now`. Outside a project the question is asked as any other.
 */
export function StewardOfferQuestion({
  question,
  askedBy,
  onAnswer,
  disabled,
  ref,
}: {
  question: Question;
  askedBy: string;
  onAnswer: (answers: ReplyAnswers, text: string) => void;
  disabled: boolean;
  ref?: Ref<Focusable>;
}) {
  const steward = useSteward();
  const heading = useRef<HTMLHeadingElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => heading.current?.focus() }));
  const label = (value: string) =>
    question.question_options?.find((o) => o.option_value === value)?.option_label ?? value;
  const answer = (value: string) => {
    const answers = { answer_to: askedBy, given_answers: [{ answered_key: STEWARD_KEY, answer_values: [value] }] };
    onAnswer(answers, answersText([question], answers));
  };
  return (
    <section className="callout choice-question" aria-labelledby={`${askedBy}-steward`}>
      <h3 id={`${askedBy}-steward`} ref={heading} tabIndex={-1}>
        {question.question_prompt}
      </h3>
      <p className="hint">
        You see what would be shared before anything is sent. Nothing is sent if you choose not
        now.
      </p>
      <p>
        <Button
          variant="primary"
          icon={LifeBuoy}
          isDisabled={disabled || !steward}
          onPress={() =>
            steward?.offer({
              origin: { kind: "orchestrator", invocation_id: askedBy },
              onSent: () => answer(SEND),
            })
          }
        >
          {label(SEND)}
        </Button>{" "}
        <Button isDisabled={disabled} onPress={() => answer(NOT_NOW)}>
          {label(NOT_NOW)}
        </Button>
      </p>
    </section>
  );
}
