/**
 * A draft's open questions, on its card in the conversation and in the Questions section of the
 * project's documents page (docs/specs/drafting.md, docs/specs/app.md): what the drafter could not
 * read from the project's facts, such as a field's definition, its unit or its missing-value codes.
 *
 * The questions come in two groups. Those a model suggested an answer for come first, every one at
 * once, each in a text box that starts with the suggestion and says it came from a model; the
 * researcher checks them, changes or clears any that are wrong, and records them all with one
 * "Accept" button. A suggestion is recorded only then, as the person's answer, and a cleared box is
 * left unanswered. Those only the researcher can answer follow, a few at a time in blank boxes; the
 * parts of one README section stay on one page. Each box is labelled by its question and described
 * by what it fills. The harness records each answer for the person signed in, and the next draft
 * places it as supplied. No agent writes an answer.
 *
 * Each question links to a new conversation that asks for help with it ("Talk this through"),
 * with the message in the box, unsent (`homePath`'s `question`); the answer is still recorded here.
 *
 * On a version at the `questions` stage, which asks before the document is written, the form also
 * offers to write the document: it saves any answers typed in the blank boxes, then asks in the
 * conversation for the document to be drafted (`onWrite`). Suggestions not accepted are not sent.
 *
 * Only the latest version's questions can be answered. Once saved, the answered questions leave
 * the form, a status says so, and the next ones are shown.
 */

import "./DocumentQuestions.css";

import { Check, MessageCircle, PenLine, Save } from "lucide-react";
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
import { Link, homePath } from "../../route";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";

/** A question's suggested answer, or "" when it has none. */
function suggestion(q: DocumentQuestion): string {
  return q.suggested_answer ?? "";
}

/** How many questions only the researcher can answer are put at once. */
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

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function DocumentQuestions({
  projectId,
  document,
  version,
  name,
  onAnswered,
  onWrite,
}: {
  projectId: string;
  document: ProjectDocument;
  /** The document's latest version, whose questions are answered. */
  version: DocumentVersion;
  /** The document's name, as the card shows it. */
  name: string;
  /** Called with the project's documents as the server read them back after the answers. */
  onAnswered: (value: ProjectDocuments) => void;
  /** For a `questions` version: asks in the conversation for the document to be written. */
  onWrite?: (message: string) => void;
}) {
  const id = useId();
  const api = useProjectApi();
  const open = openQuestions(document, version);
  const [start, setStart] = useState(0);
  // What the person has typed or changed; a suggested box not touched holds its suggestion.
  const [words, setWords] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const writeMessage = `Write the ${name} from my answers.`;

  if (open.length === 0 && onWrite) {
    return (
      <p>
        {said && (
          <span role="status" className="hint">
            {said}{" "}
          </span>
        )}
        <Button icon={PenLine} onPress={() => onWrite(writeMessage)}>
          Write the {name}
        </Button>
      </p>
    );
  }

  if (open.length === 0) {
    return said ? (
      <p role="status" className="hint">
        {said}
      </p>
    ) : null;
  }

  const value = (q: DocumentQuestion) => words[q.question_id] ?? suggestion(q);
  const given = (questions: DocumentQuestion[]): GivenAnswer[] =>
    questions
      .map((q) => ({ answered_question: q.question_id, answer_text: value(q).trim() }))
      .filter((a) => a.answer_text !== "");

  const suggested = open.filter((q) => suggestion(q) !== "");
  const yours = open.filter((q) => suggestion(q) === "");
  const from = start < yours.length ? start : 0;
  const shown = yours.slice(from, pageEnd(yours, from));
  const accepting = given(suggested);
  const typed = given(shown);
  const others = yours.length - shown.length;

  /** Saves the answers typed, if any, then asks for the document to be written. */
  async function write() {
    if (saving || !onWrite) return;
    if (typed.length > 0 && !(await save(typed))) return;
    onWrite(writeMessage);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (typed.length > 0 && !saving) void save(typed);
  }

  /** Records `answers`; whether they were recorded. */
  async function save(answers: GivenAnswer[]): Promise<boolean> {
    setSaving(true);
    setFailed(null);
    try {
      const read = await api.answer(projectId, document.document_id, version.version, answers);
      const n = answers.length;
      const recorded = `Recorded ${plural(n, "answer", "answers")}.`;
      setSaid(
        onWrite
          ? `${recorded} Answer more, or write the ${name} now.`
          : `${recorded} Ask for a new draft to put ${n === 1 ? "it" : "them"} into the ${name}.`,
      );
      const sent = new Set(answers.map((a) => a.answered_question));
      setWords((was) => Object.fromEntries(Object.entries(was).filter(([q]) => !sent.has(q))));
      setStart(0);
      onAnswered(read);
      return true;
    } catch (e: unknown) {
      setFailed(
        e instanceof DecisionConflict
          ? `Your answers were not recorded: ${e.message} Read the latest version and answer again.`
          : `Your answers were not recorded: ${errorMessage(e)}`,
      );
      return false;
    } finally {
      setSaving(false);
    }
  }

  const field = (q: DocumentQuestion) => (
    <QuestionField
      key={q.question_id}
      id={`${id}-${q.question_id}`}
      question={q}
      documentId={document.document_id}
      value={value(q)}
      onChange={(text) => setWords((was) => ({ ...was, [q.question_id]: text }))}
    />
  );

  return (
    <form className="document-questions" onSubmit={submit} aria-labelledby={`${id}-title`}>
      <p id={`${id}-title`} className="document-questions-title">
        The {name} has {plural(open.length, "question", "questions")} for you
      </p>
      {suggested.length > 0 && (
        <fieldset className="field" disabled={saving}>
          <legend>Suggested answers to check ({suggested.length})</legend>
          <p className="hint">
            A model suggested these from the project&apos;s files and documents. Check each one;
            change it, or clear the box if it is wrong. Nothing is recorded until you accept.
          </p>
          {suggested.map(field)}
          <p>
            <Button icon={Check} onPress={() => void save(accepting)} isDisabled={accepting.length === 0}>
              Accept {plural(accepting.length, "suggested answer", "suggested answers")}
            </Button>
          </p>
        </fieldset>
      )}
      {yours.length > 0 && (
        <fieldset className="field" disabled={saving}>
          <legend>
            {suggested.length > 0
              ? `Only you can answer these (${yours.length})`
              : `Only you can answer ${yours.length === 1 ? "this" : "these"}`}
          </legend>
          <p className="hint">
            Answer any you can; leave the rest blank. Your answers are kept in the project
            {onWrite
              ? `, and the ${name} is written from them`
              : " and put into the next draft as you wrote them"}
            .
          </p>
          {shown.map(field)}
          <p>
            <Button type="submit" icon={Save} isDisabled={typed.length === 0}>
              Save answers
            </Button>{" "}
            {others > 0 && (
              <Button variant="quiet" onPress={() => setStart(pageEnd(yours, from))}>
                Show other questions <span className="visually-hidden">for the {name}</span>
              </Button>
            )}
          </p>
        </fieldset>
      )}
      {onWrite && (
        <p>
          <Button icon={PenLine} onPress={() => void write()} isDisabled={saving}>
            {typed.length > 0 ? "Save and write" : "Write"} the {name}
          </Button>
        </p>
      )}
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

/** One question's text box, described by what it fills and by any suggestion it started with. */
function QuestionField({
  id,
  question: q,
  documentId,
  value,
  onChange,
}: {
  id: string;
  question: DocumentQuestion;
  documentId: string;
  value: string;
  onChange: (text: string) => void;
}) {
  const offered = suggestion(q);
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
        aria-describedby={offered ? `${id}-target ${id}-suggestion` : `${id}-target`}
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="hint">
        <Link to={homePath({ question: `${documentId}/${q.question_id}` })}>
          <MessageCircle aria-hidden="true" size={16} /> Talk this through{" "}
          <span className="visually-hidden">in a new conversation: {q.question_prompt}</span>
        </Link>
      </p>
    </div>
  );
}
