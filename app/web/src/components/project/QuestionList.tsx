/**
 * A version's Questions section on the project's documents page (docs/specs/drafting.md): one
 * heading, how many are answered, and then, on the latest version, the form (`children`, the same
 * form as the draft's card in the conversation), which puts the questions still open and lists the
 * answered ones with their saved answers, folded away beneath it; on an earlier version, every
 * question listed read-only with its answer, since only the latest version's questions can be
 * answered. An answer is put into the next draft, not into this version. Whether a question is
 * answered is said in words, never by colour. A model's suggested answer is shown as a suggestion
 * until a person records an answer.
 */

import type { ReactNode } from "react";

import type { DocumentQuestion, DocumentVersion, ProjectDocument } from "../../project/api";
import { questionTarget } from "../../project/api";

export function QuestionList({
  document,
  version,
  isLatest,
  headingId,
  children,
}: {
  document: ProjectDocument;
  version: DocumentVersion;
  /** Whether this is the latest version, whose questions `children` answers. */
  isLatest: boolean;
  headingId: string;
  /** The form for the latest version's questions, which lists the answered ones too. */
  children?: ReactNode;
}) {
  if (version.questions.length === 0) return null;
  const answers = new Map((document.answers ?? []).map((a) => [a.question_id, a]));
  const answeredOnes = version.questions.filter((q) => answers.has(q.question_id));
  const total = version.questions.length;
  return (
    <section className="question-list" aria-labelledby={headingId}>
      <h3 id={headingId}>Questions</h3>
      <p className="hint">
        {answeredOnes.length} of {total} answered.{" "}
        {isLatest
          ? "Answers go into the next draft as you wrote them."
          : "These were asked of an earlier version; answer the latest version's questions instead."}
      </p>
      {isLatest ? children : <Listed questions={version.questions} answers={answers} />}
    </section>
  );
}

/**
 * Each question with what it fills and its recorded answer, or its suggestion while it has none;
 * `action`, if given, is put after each recorded answer, such as a way to change it.
 */
export function Listed({
  questions,
  answers,
  action,
}: {
  questions: DocumentQuestion[];
  answers: ReadonlyMap<string, ProjectDocument["answers"][number]>;
  action?: (question: DocumentQuestion) => ReactNode;
}) {
  return (
    <ul>
      {questions.map((q) => {
        const answer = answers.get(q.question_id);
        return (
          <li key={q.question_id}>
            <strong>{q.question_prompt}</strong> <span className="hint">({questionTarget(q)})</span>
            <br />
            {answer ? (
              <>
                Answered: <q>{answer.answer_text}</q>
                {action && <> {action(q)}</>}
              </>
            ) : (
              <>
                Not answered yet.
                {q.suggested_answer && (
                  <>
                    {" "}
                    Suggested by a model, not yet confirmed: <q>{q.suggested_answer}</q>
                  </>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
