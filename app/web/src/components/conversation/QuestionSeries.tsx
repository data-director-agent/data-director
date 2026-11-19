/**
 * The questions a reply asks (docs/specs/app.md), put to the researcher one at a time as form
 * fields: a choice question as radio buttons, or checkboxes when several options may be chosen,
 * with "Something else" and a text box where it allows an answer in their own words; a short
 * text question as a one-line text box; a long text question as a text area with a count of the
 * characters left. Each question is a fieldset whose legend is the question, and its help is the
 * fieldset's description.
 *
 * A series of several shows which question this is ("Question 2 of 5"), with Back, Skip and Next,
 * and ends with the answers to check, each with a button to change it, before they are sent
 * together. Any question may be skipped; at least one must be answered. A lone question is
 * answered and sent in place. On moving to another question the focus moves to its legend.
 *
 * Only the latest turn's questions can be answered. Sending them sends the answers in words as
 * the message, beside the answers themselves, which the harness checks against the questions. The
 * researcher may ignore them and type in the message box instead. Earlier questions are shown as
 * they were answered, marked with an icon and words, never by colour alone.
 */

import "./QuestionSeries.css";

import { ArrowLeft, ArrowRight, Check, Pencil, SendHorizontal, SkipForward } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { type Question, type ReplyAnswers, answerSaid, answersText } from "../../conversation/question";
import { Button } from "../ui/Button";
import { type Draft, EMPTY, QuestionField, answerOf, problemOf } from "./ChoiceQuestion";

export function QuestionSeries({
  questions,
  askedBy,
  askedByName,
  onAnswer,
  disabled = false,
}: {
  questions: Question[];
  /** The invocation whose reply asks them. */
  askedBy: string;
  /** Who asks, as the researcher reads it. */
  askedByName?: string;
  onAnswer: (answers: ReplyAnswers, text: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const count = questions.length;
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  // Which question is shown: an index into `questions`, or `count` for the answers to check.
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const legend = useRef<HTMLLegendElement>(null);
  const review = useRef<HTMLHeadingElement>(null);
  // The focus moves only once the researcher has moved, never when the questions first show.
  const moved = useRef(false);

  useEffect(() => {
    if (!moved.current) return;
    (step < count ? legend.current : review.current)?.focus();
  }, [step, count]);

  const draftOf = (q: Question): Draft => drafts[q.question_key] ?? EMPTY;
  const given = questions.flatMap((q) => {
    const answer = answerOf(q, draftOf(q));
    return answer ? [answer] : [];
  });

  function change(q: Question, draft: Draft) {
    setDrafts((was) => ({ ...was, [q.question_key]: draft }));
    setError(null);
  }

  function go(to: number) {
    moved.current = true;
    setError(null);
    setStep(to);
  }

  function send() {
    if (given.length === 0 || disabled) return;
    const answers: ReplyAnswers = { answer_to: askedBy, given_answers: given };
    onAnswer(answers, answersText(questions, answers));
  }

  function next(event: FormEvent) {
    event.preventDefault();
    if (disabled) return;
    if (step >= count) {
      send();
      return;
    }
    const q = questions[step];
    if (!q) return;
    const problem = problemOf(q, draftOf(q));
    if (problem) {
      setError(problem);
      return;
    }
    if (count === 1) {
      send();
      return;
    }
    if (!answerOf(q, draftOf(q))) {
      setError("Answer the question, or skip it.");
      return;
    }
    go(step + 1);
  }

  const heading =
    count > 1 ? `${askedByName ? `${askedByName} asks` : "There are"} ${count} questions for you` : null;

  if (count === 1) {
    const q = questions[0];
    if (!q) return null;
    const ready = answerOf(q, draftOf(q)) !== null;
    return (
      <form className="choice-question question-series" onSubmit={next} aria-label={q.question_prompt}>
        <fieldset className="question-step" disabled={disabled}>
          <QuestionField question={q} draft={draftOf(q)} onChange={(d) => change(q, d)} error={error} />
        </fieldset>
        <Button type="submit" variant="primary" icon={SendHorizontal} isDisabled={!ready || disabled}>
          Send answer
        </Button>
      </form>
    );
  }

  const q = step < count ? questions[step] : undefined;
  return (
    <form className="choice-question question-series" onSubmit={next} aria-labelledby={`${id}-heading`}>
      <p className="question-series-heading" id={`${id}-heading`}>
        <strong>{heading}</strong>
      </p>
      <div className="question-progress">
        <p id={`${id}-progress`} className="hint">
          {q ? `Question ${step + 1} of ${count}` : `Check your answers: ${given.length} of ${count} answered`}
        </p>
        <progress aria-labelledby={`${id}-progress`} max={count} value={Math.min(step + (q ? 1 : 0), count)} />
      </div>
      <fieldset className="question-step" disabled={disabled}>
        {q ? (
          <QuestionField
            key={q.question_key}
            question={q}
            draft={draftOf(q)}
            onChange={(d) => change(q, d)}
            error={error}
            legendRef={legend}
          />
        ) : (
          <section aria-labelledby={`${id}-review`}>
            <h3 id={`${id}-review`} ref={review} tabIndex={-1} className="question-review-heading">
              Check your answers
            </h3>
            <dl className="question-review">
              {questions.map((asked, index) => {
                const answer = answerOf(asked, draftOf(asked));
                return (
                  <div key={asked.question_key} className="question-review-row">
                    <dt>{asked.question_prompt}</dt>
                    <dd>
                      {answer ? (
                        <span className="question-review-answer">{answerSaid(asked, answer)}</span>
                      ) : (
                        <span className="muted">Skipped</span>
                      )}
                      <Button
                        variant="quiet"
                        size="small"
                        icon={Pencil}
                        onPress={() => go(index)}
                        aria-label={`Change your answer to: ${asked.question_prompt}`}
                      >
                        Change
                      </Button>
                    </dd>
                  </div>
                );
              })}
            </dl>
            {given.length === 0 && (
              <p className="hint" role="status">
                Answer at least one question to send your answers, or type a reply below instead.
              </p>
            )}
          </section>
        )}
      </fieldset>
      <div className="question-actions">
        {step > 0 && (
          <Button icon={ArrowLeft} onPress={() => go(step - 1)} isDisabled={disabled}>
            Back
          </Button>
        )}
        {q && (
          <Button variant="quiet" icon={SkipForward} onPress={() => go(step + 1)} isDisabled={disabled}>
            Skip
          </Button>
        )}
        {q ? (
          <Button type="submit" variant="primary" icon={ArrowRight} isDisabled={disabled}>
            {step === count - 1 ? "Check answers" : "Next"}
          </Button>
        ) : (
          <Button type="submit" variant="primary" icon={SendHorizontal} isDisabled={given.length === 0 || disabled}>
            Send answers
          </Button>
        )}
      </div>
    </form>
  );
}

/** Earlier questions, read-only: each with the answer given, the options chosen marked. */
export function AskedQuestions({
  questions,
  answers,
}: {
  questions: Question[];
  /** The answers the next turn sent, or null if the researcher typed a reply instead. */
  answers: ReplyAnswers | null;
}) {
  return (
    <div className="choice-asked">
      {questions.length > 1 && <p className="choice-asked-prompt">You were asked {questions.length} questions.</p>}
      {questions.map((question) => {
        const answer = answers?.given_answers.find((a) => a.answered_key === question.question_key) ?? null;
        return (
          <div key={question.question_key} className="question-asked">
            <p className="choice-asked-prompt">{question.question_prompt}</p>
            <ul className="plain-list">
              {(question.question_options ?? []).map((o) => {
                const picked = answer?.answer_values.includes(o.option_value) ?? false;
                return (
                  <li key={o.option_value} className={picked ? "choice-picked" : undefined}>
                    {picked && <Check aria-hidden="true" size={16} />}
                    {o.option_label}
                    {picked && <span className="choice-picked-word"> (your choice)</span>}
                  </li>
                );
              })}
              {answer?.answer_words && (
                <li className="choice-picked">
                  <Check aria-hidden="true" size={16} />
                  {question.question_kind === "choice" ? "In your own words: " : "Your answer: "}
                  {answer.answer_words}
                </li>
              )}
              {answers && !answer && <li className="muted">Skipped</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
