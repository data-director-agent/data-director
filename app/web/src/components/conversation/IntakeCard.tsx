/**
 * The project intake's card (docs/specs/app.md, rule 25): Data Director's greeting and the next
 * question, at the top of the conversation, before the researcher has typed anything. The
 * questions are the harness's (`dd_sdk.intake`), read from the server with their current answers;
 * the card asks them one at a time, each drawn as a reply's choice question is (`QuestionField`).
 *
 * Next records the answer and moves on; Skip passes one question by for this visit only, so it is
 * asked again next time; **Skip these questions** dismisses the intake. Once nothing is left to
 * ask, the card says which phase the project starts at and which step is suggested first, both
 * from the progress the server answered with, named from the server's process flow.
 *
 * Asked again from the phase tracker, the card walks every question with its current answer
 * chosen, and records only what changed. Each new question, and the summary, is announced in the
 * page's polite live region; the focus moves to it only once the researcher has acted. The card
 * is not a turn and never holds up the message box below it.
 */

import "./ChoiceQuestion.css";
import "./QuestionSeries.css";
import "./IntakeCard.css";

import { ArrowRight, Check, SkipForward, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import type { ProcessFlow } from "../../flow/types";
import type { IntakeQuestion, ProjectIntake } from "../../project/api";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { type Draft, QuestionField, answerOf } from "./ChoiceQuestion";

/** The phase a project at `entry` starts at and the step suggested first, by their names. */
function summaryOf(
  flow: ProcessFlow | null,
  intake: ProjectIntake,
): { phase: string | null; step: string | null } {
  const { entry, suggested } = intake.progress;
  const startsAt = flow?.entries.find((e) => e.number === entry)?.starts_at;
  const phase = flow?.phases.find((p) => p.number === startsAt) ?? null;
  const step = flow?.phases.flatMap((p) => p.steps).find((s) => s.id === suggested) ?? null;
  return {
    phase: phase ? `Phase ${phase.number}, ${phase.name}` : null,
    step: step ? step.label : null,
  };
}

function sameValues(a: readonly string[], b: readonly string[] | null): boolean {
  return b !== null && a.length === b.length && a.every((v) => b.includes(v));
}

export function IntakeCard({
  intake,
  again = false,
  flow,
  onAnswer,
  onDismiss,
  onClose,
  onAnnounce,
}: {
  intake: ProjectIntake;
  /** Asked again from the phase tracker: every question, with its current answer chosen. */
  again?: boolean;
  flow: ProcessFlow | null;
  /** Records an answer; resolves with the intake anew, or rejects saying why it was refused. */
  onAnswer: (questionId: string, values: string[]) => Promise<ProjectIntake>;
  /** Records the intake dismissed. */
  onDismiss: () => void;
  /** Closes the card, recording nothing. */
  onClose: () => void;
  onAnnounce: (text: string) => void;
}) {
  const id = useId();
  // The questions passed by in this visit: skipped, or, asked again, answered.
  const [passed, setPassed] = useState<ReadonlySet<string>>(new Set());
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const legend = useRef<HTMLLegendElement>(null);
  const ending = useRef<HTMLHeadingElement>(null);
  // The focus moves only once the researcher has acted, never when the card first shows.
  const moved = useRef(false);

  const shown: IntakeQuestion | undefined = intake.questions.find(
    (q) => !passed.has(q.question_id) && (again || q.answer_values === null),
  );
  const draftOf = (q: IntakeQuestion): Draft =>
    drafts[q.question_id] ?? { values: q.answer_values ?? [], words: "" };
  const complete = intake.state === "complete";
  const summary = summaryOf(flow, intake);
  const said = shown
    ? shown.question.question_prompt
    : complete
      ? [
          summary.phase && `Your project starts at ${summary.phase}.`,
          summary.step && `Suggested first step: ${summary.step}.`,
        ]
          .filter(Boolean)
          .join(" ") || "Thank you: your answers are recorded."
      : "You can answer the setup questions later from the phase tracker.";

  useEffect(() => {
    onAnnounce(moved.current || !shown ? said : `Data Director asks: ${said}`);
    if (moved.current) (shown ? legend.current : ending.current)?.focus();
    // Announced when what the card shows changes, not when the callback does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown?.question_id, said]);

  function pass(questionId: string) {
    moved.current = true;
    setError(null);
    setPassed((was) => new Set([...was, questionId]));
  }

  async function next(event: FormEvent) {
    event.preventDefault();
    if (!shown || busy) return;
    const answer = answerOf(shown.question, draftOf(shown));
    if (!answer) {
      setError("Choose an answer, or skip the question.");
      return;
    }
    if (again && sameValues(answer.answer_values, shown.answer_values)) {
      pass(shown.question_id);
      return;
    }
    setBusy(true);
    try {
      await onAnswer(shown.question_id, answer.answer_values);
      // Asked again, the answered question is passed by; else the server's answer moves on.
      if (again) pass(shown.question_id);
      else {
        moved.current = true;
        setError(null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="choice-question intake-card" aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} className="intake-card-heading">
        {again ? "Setup questions" : "Data Director"}
      </h3>
      {!again && (
        <p>
          Before you start, a few questions place your project in the process. Answer, skip them,
          or type below at any time.
        </p>
      )}
      {shown ? (
        <form onSubmit={(e) => void next(e)} aria-labelledby={`${id}-heading`}>
          <fieldset className="question-step" disabled={busy}>
            <QuestionField
              key={shown.question_id}
              question={shown.question}
              draft={draftOf(shown)}
              onChange={(draft) => {
                setDrafts((was) => ({ ...was, [shown.question_id]: draft }));
                setError(null);
              }}
              error={error}
              legendRef={legend}
            />
          </fieldset>
          <div className="question-actions">
            <Button
              variant="quiet"
              icon={SkipForward}
              onPress={() => pass(shown.question_id)}
              isDisabled={busy}
            >
              Skip
            </Button>
            <Button type="submit" variant="primary" icon={ArrowRight} isPending={busy}>
              Next
            </Button>
            <Button variant="quiet" icon={X} onPress={again ? onClose : onDismiss} isDisabled={busy}>
              Skip these questions
            </Button>
          </div>
        </form>
      ) : (
        <div className="intake-card-ending">
          <h4 ref={ending} tabIndex={-1}>
            {complete ? "Where your project starts" : "Questions skipped"}
          </h4>
          {complete ? (
            <>
              {summary.phase && (
                <p>
                  Your project starts at <strong>{summary.phase}</strong>.
                </p>
              )}
              {summary.step && (
                <p>
                  Suggested first step: <strong>{summary.step}</strong>.
                </p>
              )}
              {!summary.phase && !summary.step && <p>Thank you: your answers are recorded.</p>}
            </>
          ) : (
            <p>You can answer the setup questions later from the phase tracker.</p>
          )}
          <Button icon={Check} onPress={onClose}>
            Close
          </Button>
        </div>
      )}
    </section>
  );
}
