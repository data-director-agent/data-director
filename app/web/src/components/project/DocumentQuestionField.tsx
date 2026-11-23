/**
 * One of a draft's questions as a text box (`DocumentQuestions`): labelled by the question and
 * described by what it fills, by any suggestion it started with, by a count of the characters left
 * against the longest answer the harness keeps, and, while it holds a change not saved, by
 * "Not saved yet". The box never cuts what is typed or pasted: over the limit, the count says by
 * how much, the box is marked invalid, and the form refuses to save it.
 *
 * A question answered with a list of values (`answer_kind` `list`) takes one value on each line,
 * says what will be recorded, warns when a line reads like several values or a note, and offers
 * "no value means missing" (`listAnswer`). Its help, if any, shows under the question.
 */

import { MessageCircle, Undo2 } from "lucide-react";

import { charactersIn } from "../../conversation/question";
import { type DocumentQuestion, questionTarget } from "../../project/api";
import { suggestionSource } from "../../project/suggestion";
import { Link, homePath } from "../../route";
import { Button } from "../ui/Button";
import { AnswerBox, answerLength, listDescriptions } from "./AnswerBox";
import { suggestion } from "./useAnswerDrafts";

function characters(n: number): string {
  return `${n} ${n === 1 ? "character" : "characters"}`;
}

/** Whether `text`, as it would be saved, is longer than `maxLength`. */
export function overLimit(text: string, maxLength: number): boolean {
  return charactersIn(text.trim()) > maxLength;
}

export function DocumentQuestionField({
  id,
  question: q,
  documentId,
  value,
  maxLength,
  unsaved,
  onChange,
  onKeep,
}: {
  id: string;
  question: DocumentQuestion;
  documentId: string;
  value: string;
  /** The longest answer the harness keeps, in characters. */
  maxLength: number;
  /** Whether the box holds a change not saved. */
  unsaved: boolean;
  onChange: (text: string) => void;
  /** For a question put back to change its saved answer: keeps the saved answer instead. */
  onKeep?: () => void;
}) {
  const offered = onKeep ? "" : suggestion(q);
  const left = maxLength - answerLength(q, value);
  const described = [
    q.question_help && `${id}-help`,
    `${id}-target`,
    ...listDescriptions(id, q, value),
    offered && `${id}-suggestion`,
    `${id}-count`,
    unsaved && `${id}-unsaved`,
  ].filter(Boolean);
  return (
    <div className="field document-question">
      <label htmlFor={id}>{q.question_prompt}</label>
      {q.question_help && (
        <p className="hint" id={`${id}-help`}>
          {q.question_help}
        </p>
      )}
      <p className="hint" id={`${id}-target`}>
        Fills: {questionTarget(q)}
      </p>
      {offered && (
        <p className="hint">
          <span id={`${id}-suggestion`}>
            {value === offered
              ? `Suggested ${suggestionSource(q)}; check it before you accept.`
              : <>You changed the suggestion {suggestionSource(q)}: <q>{offered}</q>.</>}
          </span>
          {value !== offered && (
            <>
              {" "}
              <Button variant="quiet" onPress={() => onChange(offered)}>
                Put the suggestion back <span className="visually-hidden">for: {q.question_prompt}</span>
              </Button>
            </>
          )}
        </p>
      )}
      <AnswerBox
        id={id}
        question={q}
        value={value}
        describedBy={described.join(" ")}
        invalid={left < 0}
        onChange={onChange}
      />
      <p className="hint document-question-state">
        <span id={`${id}-count`}>
          {left >= 0 ? `${characters(left)} left.` : `${characters(-left)} over the limit of ${maxLength}.`}
        </span>
        {unsaved && (
          <>
            {" "}
            <span id={`${id}-unsaved`} className="status status-warn">
              Not saved yet
            </span>
          </>
        )}
      </p>
      <p className="hint">
        {onKeep && (
          <>
            <Button variant="quiet" size="small" icon={Undo2} onPress={onKeep}>
              Keep the saved answer <span className="visually-hidden">to: {q.question_prompt}</span>
            </Button>{" "}
          </>
        )}
        <Link to={homePath({ question: `${documentId}/${q.question_id}` })}>
          <MessageCircle aria-hidden="true" size={16} /> Talk this through{" "}
          <span className="visually-hidden">in a new conversation: {q.question_prompt}</span>
        </Link>
      </p>
    </div>
  );
}
