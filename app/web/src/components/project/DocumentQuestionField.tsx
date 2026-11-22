/**
 * One of a draft's questions as a text box (`DocumentQuestions`): labelled by the question and
 * described by what it fills, by any suggestion it started with, by a count of the characters left
 * against the longest answer the harness keeps, and, while it holds a change not saved, by
 * "Not saved yet". The box never cuts what is typed or pasted: over the limit, the count says by
 * how much, the box is marked invalid, and the form refuses to save it.
 */

import { MessageCircle, Undo2 } from "lucide-react";

import { charactersIn } from "../../conversation/question";
import { type DocumentQuestion, questionTarget } from "../../project/api";
import { Link, homePath } from "../../route";
import { Button } from "../ui/Button";
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
  const left = maxLength - charactersIn(value.trim());
  const described = [
    `${id}-target`,
    offered && `${id}-suggestion`,
    `${id}-count`,
    unsaved && `${id}-unsaved`,
  ].filter(Boolean);
  return (
    <div className="field document-question">
      <label htmlFor={id}>{q.question_prompt}</label>
      <p className="hint" id={`${id}-target`}>
        Fills: {questionTarget(q)}
      </p>
      {offered && (
        <p className="hint">
          <span id={`${id}-suggestion`}>
            {value === offered
              ? "Suggested by a model; check it before you accept."
              : <>You changed a model&apos;s suggestion: <q>{offered}</q>.</>}
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
      <textarea
        id={id}
        aria-describedby={described.join(" ")}
        {...(left < 0 ? { "aria-invalid": true } : {})}
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
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
