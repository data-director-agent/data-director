/**
 * One question put to the researcher as a form field (docs/specs/app.md, rule 21): a choice
 * question as radio buttons, or checkboxes when several options may be chosen, each option a card
 * the whole of which can be clicked, with "Something else" and a text box where it allows an
 * answer in their own words; a short text question as a one-line text box; a long text question
 * as a text area with a count of the characters left. The question is a fieldset whose legend is
 * the question, and its help is the fieldset's description.
 *
 * A reply's questions (`QuestionSeries`) and the project intake's (`IntakeCard`) are both drawn
 * with it.
 */

import "./ChoiceQuestion.css";

import { type Ref, useId } from "react";

import {
  LONG_TEXT_MAX,
  type Question,
  type QuestionAnswer,
  SHORT_TEXT_MAX,
} from "../../conversation/question";

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

/** Why a draft cannot be kept as it is, or null if it can (an empty draft is a skip). */
export function problemOf(question: Question, draft: Draft): string | null {
  const other = question.question_other ? otherValue(question) : null;
  if (question.question_kind === "choice" && other !== null && draft.values.includes(other)) {
    if (!draft.words.trim()) return "Say what your answer is, or choose another option.";
  }
  return null;
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

  function toggle(value: string, checked: boolean) {
    const values = !multiple ? [value] : checked ? [...draft.values, value] : draft.values.filter((v) => v !== value);
    onChange({ ...draft, values });
  }

  const how =
    question.question_kind === "choice"
      ? multiple
        ? "Choose one or more."
        : "Choose one."
      : question.question_kind === "short_text"
        ? "Answer in a line."
        : "Answer in a few sentences.";

  const options = [
    ...(question.question_options ?? []).map((o) => ({
      value: o.option_value,
      label: o.option_label,
      help: o.option_help ?? null,
    })),
    ...(other !== null ? [{ value: other, label: "Something else", help: null }] : []),
  ];

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
          <input
            type="text"
            id={`${id}-words`}
            maxLength={SHORT_TEXT_MAX}
            value={draft.words}
            onChange={(e) => onChange({ ...draft, words: e.target.value })}
            {...(error ? { "aria-invalid": true, "aria-describedby": `${id}-error` } : {})}
          />
        </div>
      )}
      {question.question_kind === "short_text" && (
        <>
          <label className="visually-hidden" htmlFor={`${id}-words`}>
            Your answer
          </label>
          <input
            type="text"
            id={`${id}-words`}
            maxLength={SHORT_TEXT_MAX}
            value={draft.words}
            onChange={(e) => onChange({ ...draft, words: e.target.value })}
          />
        </>
      )}
      {question.question_kind === "long_text" && (
        <>
          <label className="visually-hidden" htmlFor={`${id}-words`}>
            Your answer
          </label>
          <textarea
            id={`${id}-words`}
            rows={5}
            maxLength={LONG_TEXT_MAX}
            value={draft.words}
            aria-describedby={`${id}-count`}
            onChange={(e) => onChange({ ...draft, words: e.target.value })}
          />
          <p className="hint" id={`${id}-count`}>
            {LONG_TEXT_MAX - draft.words.length} characters left.
          </p>
        </>
      )}
    </fieldset>
  );
}
