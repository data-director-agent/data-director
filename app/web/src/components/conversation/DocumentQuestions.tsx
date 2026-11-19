/**
 * A draft's open questions, on its card in the conversation (docs/specs/drafting.md,
 * docs/specs/app.md): what the drafter could not read from the project's facts, such as a field's
 * definition, its unit or its missing-value codes. A few are shown at a time, each with a text box
 * labelled by the question and described by what it fills; the parts of one README section stay on
 * one page. The researcher answers any of them and saves; blank boxes are left as they are. The harness records each answer for the person signed
 * in, and the next draft places it as supplied. No agent writes an answer.
 *
 * A question may carry a model's suggested answer, such as a field's likely definition or unit.
 * It is shown beside the box, which it never fills by itself: the researcher copies it in with
 * "Use suggestion", may change it, and it is recorded only when they save.
 *
 * Only the latest version's questions can be answered. Once saved, the answered questions leave
 * the list, a status says so, and the next ones are shown.
 */

import "./ChoiceQuestion.css";

import { Save } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import {
  DecisionConflict,
  type DocumentQuestion,
  type GivenAnswer,
  type ProjectDocument,
  type ProjectDocuments,
  type DocumentVersion,
  openQuestions,
  questionTarget,
  useProjectApi,
} from "../../project/api";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";

/** A question's suggested answer, or "" when it has none. */
function suggestion(q: DocumentQuestion): string {
  return q.suggested_answer ?? "";
}

/** How many questions are put at once: enough to make progress, few enough to read. */
export const QUESTIONS_AT_ONCE = 3;

/**
 * Where the page of questions starting at `from` ends: after QUESTIONS_AT_ONCE questions, or later
 * if that would split the parts of one README section, which are read together.
 */
function pageEnd(open: DocumentQuestion[], from: number): number {
  let end = Math.min(from + QUESTIONS_AT_ONCE, open.length);
  const last = open[end - 1];
  while (
    end < open.length &&
    last?.gap_part !== undefined &&
    open[end]?.gap_part !== undefined &&
    open[end]?.gap_section === last.gap_section
  )
    end += 1;
  return end;
}

export function DocumentQuestions({
  projectId,
  document,
  version,
  name,
  onAnswered,
}: {
  projectId: string;
  document: ProjectDocument;
  /** The document's latest version, whose questions are answered. */
  version: DocumentVersion;
  /** The document's name, as the card shows it. */
  name: string;
  /** Called with the project's documents as the server read them back after the answers. */
  onAnswered: (value: ProjectDocuments) => void;
}) {
  const id = useId();
  const api = useProjectApi();
  const open = openQuestions(document, version);
  const [start, setStart] = useState(0);
  const [words, setWords] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  if (open.length === 0) {
    return said ? (
      <p role="status" className="hint">
        {said}
      </p>
    ) : null;
  }

  const from = start < open.length ? start : 0;
  const shown: DocumentQuestion[] = open.slice(from, pageEnd(open, from));
  const given: GivenAnswer[] = shown
    .map((q) => ({ answered_question: q.question_id, answer_text: (words[q.question_id] ?? "").trim() }))
    .filter((a) => a.answer_text !== "");
  const others = open.length - shown.length;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (given.length === 0 || saving) return;
    setSaving(true);
    setFailed(null);
    try {
      const value = await api.answer(projectId, document.document_id, version.version, given);
      const n = given.length;
      setSaid(
        `Recorded ${n} ${n === 1 ? "answer" : "answers"}. Ask for a new draft to put ${
          n === 1 ? "it" : "them"
        } into the ${name}.`,
      );
      const sent = new Set(given.map((a) => a.answered_question));
      setWords((was) => Object.fromEntries(Object.entries(was).filter(([q]) => !sent.has(q))));
      setStart(0);
      onAnswered(value);
    } catch (e: unknown) {
      setFailed(
        e instanceof DecisionConflict
          ? `Your answers were not recorded: ${e.message} Read the latest version and answer again.`
          : `Your answers were not recorded: ${errorMessage(e)}`,
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="choice-question document-questions" onSubmit={(e) => void submit(e)} aria-labelledby={`${id}-legend`}>
      <fieldset className="field" disabled={saving}>
        <legend id={`${id}-legend`}>
          {open.length === 1
            ? `The ${name} has 1 question for you`
            : `The ${name} has ${open.length} questions for you`}
        </legend>
        <p className="hint">
          Only you know these. Answer any you can; leave the rest blank. Your answers are kept in
          the project and put into the next draft as you wrote them.
        </p>
        {shown.map((q) => (
          <div className="field" key={q.question_id}>
            <label htmlFor={`${id}-${q.question_id}`}>{q.question_prompt}</label>
            <p className="hint" id={`${id}-${q.question_id}-target`}>
              Fills: {questionTarget(q)}
            </p>
            {suggestion(q) && (
              <p className="hint">
                <span id={`${id}-${q.question_id}-suggestion`}>
                  Suggested by a model: <q>{suggestion(q)}</q>. Check it before you use it.
                </span>{" "}
                <Button
                  variant="quiet"
                  onPress={() => setWords((was) => ({ ...was, [q.question_id]: suggestion(q) }))}
                >
                  Use suggestion <span className="visually-hidden">for: {q.question_prompt}</span>
                </Button>
              </p>
            )}
            <textarea
              id={`${id}-${q.question_id}`}
              aria-describedby={
                suggestion(q)
                  ? `${id}-${q.question_id}-target ${id}-${q.question_id}-suggestion`
                  : `${id}-${q.question_id}-target`
              }
              rows={2}
              value={words[q.question_id] ?? ""}
              onChange={(e) => setWords((was) => ({ ...was, [q.question_id]: e.target.value }))}
            />
          </div>
        ))}
      </fieldset>
      <p>
        <Button type="submit" icon={Save} isDisabled={given.length === 0 || saving}>
          Save answers
        </Button>{" "}
        {others > 0 && (
          <Button
            variant="quiet"
            onPress={() => setStart(pageEnd(open, from))}
            isDisabled={saving}
          >
            Show other questions <span className="visually-hidden">for the {name}</span>
          </Button>
        )}
      </p>
      {failed && (
        <p role="alert" className="callout status-warn">
          {failed}
        </p>
      )}
      <p role="status" className="hint">
        {said}
      </p>
    </form>
  );
}
