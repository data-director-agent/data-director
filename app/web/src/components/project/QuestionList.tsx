/**
 * What a version asks the researcher, read-only, on the project's documents page
 * (docs/specs/drafting.md): each question, what it fills, and the answer recorded for it, if any.
 * Questions are answered on the draft's card in the conversation; an answer is put into the next
 * draft, not into this version. Whether a question is answered is said in words, never by colour.
 */

import type { DocumentVersion, ProjectDocument } from "../../project/api";
import { questionTarget } from "../../project/api";

export function QuestionList({
  document,
  version,
  headingId,
}: {
  document: ProjectDocument;
  version: DocumentVersion;
  headingId: string;
}) {
  if (version.questions.length === 0) return null;
  const answers = new Map((document.answers ?? []).map((a) => [a.question_id, a]));
  const answered = version.questions.filter((q) => answers.has(q.question_id)).length;
  return (
    <section className="question-list" aria-labelledby={headingId}>
      <h3 id={headingId}>Questions for the researcher</h3>
      <p className="hint">
        {answered} of {version.questions.length} answered. Answer them on the draft in the
        conversation; the answers go into the next draft, as you wrote them.
      </p>
      <ul>
        {version.questions.map((q) => {
          const answer = answers.get(q.question_id);
          return (
            <li key={q.question_id}>
              <strong>{q.question_prompt}</strong>{" "}
              <span className="hint">({questionTarget(q)})</span>
              <br />
              {answer ? (
                <>
                  Answered: <q>{answer.answer_text}</q>
                </>
              ) : (
                "Not answered yet."
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
