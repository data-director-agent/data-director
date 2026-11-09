/**
 * A reply's choice question (docs/specs/app.md): radio buttons when one option may be chosen,
 * checkboxes when several may, and "Something else" with a text box where the question allows an
 * answer in the researcher's own words. The controls are grouped in a fieldset whose legend is the
 * question, and each option's help is its description.
 *
 * Only the latest turn's question can be answered. Sending it sends the labels chosen as the
 * message, beside the answer itself, which the harness checks against the question. The
 * researcher may ignore it and type in the message box instead. An earlier question is shown as
 * it was answered, marked with an icon and words, never by colour alone.
 */

import "./ChoiceQuestion.css";

import { Check, SendHorizontal } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import {
  type ChoiceAnswer,
  type ChoiceQuestion as Question,
  answerText,
} from "../../conversation/question";
import { Button } from "../ui/Button";

/** The value of "Something else", which no option has. */
function otherValue(question: Question): string {
  const taken = new Set(question.question_options.map((o) => o.option_value));
  let value = "other";
  while (taken.has(value)) value = `_${value}`;
  return value;
}

export function ChoiceQuestion({
  question,
  askedBy,
  onAnswer,
  disabled = false,
}: {
  question: Question;
  /** The invocation whose reply asks it. */
  askedBy: string;
  onAnswer: (answer: ChoiceAnswer, text: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const multiple = Boolean(question.question_multiple);
  const other = question.question_other ? otherValue(question) : null;
  const [chosen, setChosen] = useState<string[]>([]);
  const [words, setWords] = useState("");

  const choosingOther = other !== null && chosen.includes(other);
  const ready = chosen.length > 0 && (!choosingOther || words.trim() !== "");

  function toggle(value: string, checked: boolean) {
    if (!multiple) setChosen([value]);
    else setChosen((was) => (checked ? [...was, value] : was.filter((v) => v !== value)));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || disabled) return;
    const answer: ChoiceAnswer = {
      answer_to: askedBy,
      answer_values: chosen.filter((v) => v !== other),
      ...(choosingOther ? { answer_other: words.trim() } : {}),
    };
    onAnswer(answer, answerText(question, answer));
  }

  const options = [
    ...question.question_options.map((o) => ({
      value: o.option_value,
      label: o.option_label,
      help: o.option_help ?? null,
    })),
    ...(other !== null ? [{ value: other, label: "Something else", help: null }] : []),
  ];

  return (
    <form className="choice-question" onSubmit={submit} aria-labelledby={`${id}-legend`}>
      <fieldset className="field" disabled={disabled}>
        <legend id={`${id}-legend`}>{question.question_prompt}</legend>
        <p className="hint">{multiple ? "Choose one or more." : "Choose one."} Or type a reply below instead.</p>
        {options.map(({ value, label, help }) => (
          <div className="field-check choice-option" key={value}>
            <input
              type={multiple ? "checkbox" : "radio"}
              id={`${id}-${value}`}
              name={`${id}-choice`}
              value={value}
              checked={chosen.includes(value)}
              onChange={(e) => toggle(value, e.target.checked)}
              {...(help ? { "aria-describedby": `${id}-${value}-help` } : {})}
            />
            <label htmlFor={`${id}-${value}`}>
              {label}
              {help && (
                <span className="hint choice-help" id={`${id}-${value}-help`}>
                  {help}
                </span>
              )}
            </label>
          </div>
        ))}
        {choosingOther && (
          <div className="field choice-other">
            <label htmlFor={`${id}-words`}>Your answer</label>
            <input
              type="text"
              id={`${id}-words`}
              maxLength={500}
              value={words}
              onChange={(e) => setWords(e.target.value)}
            />
          </div>
        )}
      </fieldset>
      <Button type="submit" icon={SendHorizontal} isDisabled={!ready || disabled}>
        Send answer
      </Button>
    </form>
  );
}

/** An earlier question, read-only: its options, with the one or ones chosen marked. */
export function AskedQuestion({
  question,
  answer,
}: {
  question: Question;
  /** The answer the next turn sent, or null if the researcher typed a reply instead. */
  answer: ChoiceAnswer | null;
}) {
  return (
    <div className="choice-asked">
      <p className="choice-asked-prompt">{question.question_prompt}</p>
      <ul className="plain-list">
        {question.question_options.map((o) => {
          const picked = answer?.answer_values.includes(o.option_value) ?? false;
          return (
            <li key={o.option_value} className={picked ? "choice-picked" : undefined}>
              {picked && <Check aria-hidden="true" size={16} />}
              {o.option_label}
              {picked && <span className="choice-picked-word"> (your choice)</span>}
            </li>
          );
        })}
        {answer?.answer_other && (
          <li className="choice-picked">
            <Check aria-hidden="true" size={16} />
            In your own words: {answer.answer_other}
          </li>
        )}
      </ul>
    </div>
  );
}
