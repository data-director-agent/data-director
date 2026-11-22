/**
 * One question put to the researcher as a form field (docs/specs/app.md, rule 21): a choice
 * question as radio buttons, or checkboxes when several options may be chosen, each option a card
 * the whole of which can be clicked, with "Something else" and a text box where it allows an
 * answer in their own words; a short text question as a one-line text box, offering its suggested
 * answers where it has them (`SuggestedAnswer`); a long text question as a text area. Every box
 * for an answer in their own words counts the characters left against the limit the harness holds
 * answers to, and never cuts what is typed or pasted: an answer over the limit is kept whole and
 * refused with a message saying by how much (`problemOf`). The question is a fieldset whose
 * legend is the question, and its help is the fieldset's description.
 *
 * A reply's questions (`QuestionSeries`) and the project intake's (`IntakeCard`) are both drawn
 * with it.
 */

import "./ChoiceQuestion.css";

import { type Ref, useId } from "react";

import {
  LONG_TEXT_MAX,
  charactersIn,
  type Question,
  type QuestionAnswer,
  SHORT_TEXT_MAX,
} from "../../conversation/question";
import { SuggestedAnswer } from "./SuggestedAnswer";

/** What the researcher has entered for one question so far. */
export interface Draft {
  values: string[];
  words: string;
}

export const EMPTY: Draft = { values: [], words: "" };

/** The value of "Something else", which no option has. */
export function otherValue(question: Question): string {
  const taken = new Set((question.question_options ?? []).map((o) => o.option_value));
  let value = "other";
  while (taken.has(value)) value = `_${value}`;
  return value;
}

/** The answer a draft gives, or null if it gives none. */
export function answerOf(question: Question, draft: Draft): QuestionAnswer | null {
  const words = draft.words.trim();
  if (question.question_kind !== "choice") {
    return words ? { answered_key: question.question_key, answer_values: [], answer_words: words } : null;
  }
  const other = question.question_other ? otherValue(question) : null;
  const choosingOther = other !== null && draft.values.includes(other);
  const values = draft.values.filter((v) => v !== other);
  if (values.length === 0 && !(choosingOther && words)) return null;
  return {
    answered_key: question.question_key,
    answer_values: values,
    ...(choosingOther && words ? { answer_words: words } : {}),
  };
}

/** The longest answer in the researcher's own words that `question` takes. */
function wordsMax(question: Question): number {
  return question.question_kind === "long_text" ? LONG_TEXT_MAX : SHORT_TEXT_MAX;
}

/** How many characters of the answer in the researcher's own words are kept, as `answerOf` does,
 * counted as the harness counts them (`charactersIn`). */
function wordsLength(draft: Draft): number {
  return charactersIn(draft.words.trim());
}

function characters(n: number): string {
  return `${n} ${n === 1 ? "character" : "characters"}`;
}

/** Why a draft cannot be kept as it is, or null if it can (an empty draft is a skip). */
export function problemOf(question: Question, draft: Draft): string | null {
  const other = question.question_other ? otherValue(question) : null;
  const choosingOther = other !== null && draft.values.includes(other);
  if (question.question_kind === "choice" && choosingOther && !draft.words.trim()) {
    return "Say what your answer is, or choose another option.";
  }
  const over = wordsLength(draft) - wordsMax(question);
  if ((question.question_kind !== "choice" || choosingOther) && over > 0) {
    return `Your answer is ${characters(over)} over the limit of ${wordsMax(question)}. Shorten it to send it.`;
  }
  return null;
}

/** How many characters are left, or how far over the limit the answer is, said beside its box. */
function WordsCount({ id, question, draft }: { id: string; question: Question; draft: Draft }) {
  const left = wordsMax(question) - wordsLength(draft);
  return (
    <p className="hint" id={id}>
      {left >= 0 ? `${characters(left)} left.` : `${characters(-left)} over the limit of ${wordsMax(question)}.`}
    </p>
  );
}

/** How to answer `question`, said before its controls. */
function howToAnswer(question: Question, multiple: boolean): string {
  if (question.question_kind === "choice") return multiple ? "Choose one or more." : "Choose one.";
  return question.question_kind === "short_text" ? "Answer in a line." : "Answer in a few sentences.";
}

/** The options `question` offers, with "Something else" last where it takes other answers. */
function optionsOf(question: Question, other: string | null) {
  return [
    ...(question.question_options ?? []).map((o) => ({
      value: o.option_value,
      label: o.option_label,
      help: o.option_help ?? null,
    })),
    ...(other !== null ? [{ value: other, label: "Something else", help: null }] : []),
  ];
}

/** One question's field: the controls, inside a fieldset whose legend is the question. */
export function QuestionField({
  question,
  draft,
  onChange,
  error,
  legendRef,
  lead,
}: {
  question: Question;
  draft: Draft;
  onChange: (draft: Draft) => void;
  error: string | null;
  legendRef?: Ref<HTMLLegendElement>;
  /** Words before the question in the legend, such as which of several it is. */
  lead?: string;
}) {
  const id = useId();
  const multiple = Boolean(question.question_multiple);
  const other = question.question_kind === "choice" && question.question_other ? otherValue(question) : null;
  const choosingOther = other !== null && draft.values.includes(other);
  const described = [question.question_help && `${id}-help`, `${id}-how`, error && `${id}-error`]
    .filter(Boolean)
    .join(" ");
  // What every box for an answer in their own words shares: described by its count, then any error.
  const words = {
    id: `${id}-words`,
    value: draft.words,
    onChange: (e: { target: { value: string } }) => onChange({ ...draft, words: e.target.value }),
    "aria-describedby": [`${id}-count`, error && `${id}-error`].filter(Boolean).join(" "),
    ...(error ? { "aria-invalid": true } : {}),
  };
  const count = <WordsCount id={`${id}-count`} question={question} draft={draft} />;

  function toggle(value: string, checked: boolean) {
    const values = !multiple ? [value] : checked ? [...draft.values, value] : draft.values.filter((v) => v !== value);
    onChange({ ...draft, values });
  }

  const how = howToAnswer(question, multiple);
  const options = optionsOf(question, other);

  return (
    <fieldset className={error ? "field field-invalid question-field" : "field question-field"} aria-describedby={described}>
      <legend ref={legendRef} tabIndex={-1}>
        {lead && <span className="question-lead">{lead}</span>}
        {question.question_prompt}
      </legend>
      {question.question_help && (
        <p className="hint" id={`${id}-help`}>
          {question.question_help}
        </p>
      )}
      <p className="hint" id={`${id}-how`}>
        {how} Or type a reply below instead.
      </p>
      {error && (
        <p id={`${id}-error`} className="field-error">
          <span className="status status-danger">Error</span> {error}
        </p>
      )}
      {question.question_kind === "choice" &&
        options.map(({ value, label, help }) => (
          <div className="field-check choice-option" key={value}>
            <input
              type={multiple ? "checkbox" : "radio"}
              id={`${id}-${value}`}
              name={`${id}-choice`}
              value={value}
              checked={draft.values.includes(value)}
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
          <input type="text" {...words} />
          {count}
        </div>
      )}
      {question.question_kind === "short_text" && question.question_suggestions && (
        <SuggestedAnswer
          id={id}
          suggestions={question.question_suggestions}
          words={draft.words}
          onWords={(words) => onChange({ ...draft, words })}
          count={count}
          errorId={error ? `${id}-error` : null}
        />
      )}
      {question.question_kind === "short_text" && !question.question_suggestions && (
        <>
          <label className="visually-hidden" htmlFor={`${id}-words`}>
            Your answer
          </label>
          <input type="text" {...words} />
          {count}
        </>
      )}
      {question.question_kind === "long_text" && (
        <>
          <label className="visually-hidden" htmlFor={`${id}-words`}>
            Your answer
          </label>
          <textarea rows={5} {...words} />
          {count}
        </>
      )}
    </fieldset>
  );
}
