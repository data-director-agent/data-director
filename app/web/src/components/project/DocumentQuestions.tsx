/**
 * A draft's questions, on its card in the conversation and in the Questions section of the
 * project's documents page (docs/specs/drafting.md, docs/specs/app.md): what the drafter could not
 * read from the project's facts, such as a field's definition, its unit or its missing-value codes.
 *
 * The open questions come in two groups. Those a model suggested an answer for come first, every
 * one at once, each in a text box that starts with the suggestion and says it came from a model;
 * the researcher checks them, changes or clears any that are wrong, and records them all with one
 * "Accept" button. A suggestion is recorded only then, as the person's answer, and a cleared box is
 * left unanswered. Those only the researcher can answer follow, a few at a time in blank boxes; the
 * parts of one README section stay on one page. Each box is labelled by its question, described by
 * what it fills, and counts the characters left against the longest answer the harness keeps
 * (`maxLength`, from the server); an answer over it is kept whole and refused with a message,
 * never cut. A box holding a change not saved says "Not saved yet", and the page asks before it is
 * left while any does (`useAnswerDrafts`). The harness records each answer for the person signed
 * in, and the next draft places it as supplied. No agent writes an answer.
 *
 * Each question links to a new conversation that asks for help with it ("Talk this through"),
 * with the message in the box, unsent (`homePath`'s `question`); the answer is still recorded here.
 *
 * On a version at the `questions` stage, which asks before the document is written, the form also
 * offers to write the document: it saves any answers typed in the blank boxes, then asks in the
 * conversation for the document to be drafted (`onWrite`). Suggestions not accepted are not sent.
 *
 * Only the latest version's questions can be answered. Once saved, the answered questions leave
 * the form, a status says so, and the next ones are shown. The answered questions are listed
 * beneath the form with the answers saved, read from the project log, so they are there after a
 * reload; "Change" puts one back in the form with its saved answer, and saving records a new
 * answer, which stands.
 */

import "./DocumentQuestions.css";

import { Check, PenLine, Pencil, Save } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import {
  DecisionConflict,
  type DocumentQuestion,
  type GivenAnswer,
  type ProjectDocument,
  type ProjectDocuments,
  type DocumentVersion,
  useProjectApi,
} from "../../project/api";
import { fromAPerson } from "../../project/suggestion";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { DocumentQuestionField, overLimit } from "./DocumentQuestionField";
import { Listed } from "./QuestionList";
import { suggestion, useAnswerDrafts } from "./useAnswerDrafts";

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
  maxLength,
  foldAnswered = false,
  onAnswered,
  onWrite,
}: {
  projectId: string;
  document: ProjectDocument;
  /** The document's latest version, whose questions are answered. */
  version: DocumentVersion;
  /** The document's name, as the card shows it. */
  name: string;
  /** The longest answer the harness keeps, in characters (`answer_max_length`). */
  maxLength: number;
  /** Whether the answered questions start folded away, as on the documents page. */
  foldAnswered?: boolean;
  /** Called with the project's documents as the server read them back after the answers. */
  onAnswered: (value: ProjectDocuments) => void;
  /** For a `questions` version: asks in the conversation for the document to be written. */
  onWrite?: (message: string) => void;
}) {
  const id = useId();
  const api = useProjectApi();
  const drafts = useAnswerDrafts(document, version);
  const { open, changing } = drafts;
  const [start, setStart] = useState(0);
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const writeMessage = `Write the ${name} from my answers.`;
  const answered = (
    <SavedAnswers
      document={document}
      version={version}
      changing={changing}
      folded={foldAnswered}
      onChange={(q) => {
        drafts.change(q);
        setStart(0);
      }}
    />
  );

  if (open.length === 0) {
    return (
      <>
        {(said || onWrite) && (
          <p>
            {said && (
              <span role="status" className="hint">
                {said}{" "}
              </span>
            )}
            {onWrite && (
              <Button icon={PenLine} onPress={() => onWrite(writeMessage)}>
                Write the {name}
              </Button>
            )}
          </p>
        )}
        {answered}
      </>
    );
  }

  const given = (questions: DocumentQuestion[]): GivenAnswer[] =>
    questions
      .map((q) => ({ answered_question: q.question_id, answer_text: drafts.value(q).trim() }))
      .filter((a) => a.answer_text !== "");

  const isChanging = (q: DocumentQuestion) => changing.has(q.question_id);
  const suggested = open.filter((q) => suggestion(q) !== "" && !isChanging(q));
  const yours = open.filter((q) => suggestion(q) === "" || isChanging(q));
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

  /** Records `answers`; whether they were recorded. An answer over the limit sends nothing. */
  async function save(answers: GivenAnswer[]): Promise<boolean> {
    const over = answers.filter((a) => overLimit(a.answer_text, maxLength)).length;
    if (over > 0) {
      setFailed(
        `Your answers were not recorded: ${plural(over, "answer is", "answers are")} over the limit of ${maxLength} characters. Shorten ${over === 1 ? "it" : "them"} and save again.`,
      );
      return false;
    }
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
      drafts.saved(answers.map((a) => a.answered_question));
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
    <DocumentQuestionField
      key={q.question_id}
      id={`${id}-${q.question_id}`}
      question={q}
      documentId={document.document_id}
      value={drafts.value(q)}
      maxLength={maxLength}
      unsaved={drafts.unsaved(q)}
      onChange={(text) => drafts.type(q, text)}
      {...(isChanging(q) ? { onKeep: () => drafts.keep(q) } : {})}
    />
  );

  return (
    <>
      <form className="document-questions" onSubmit={submit} aria-labelledby={`${id}-title`}>
        <p id={`${id}-title`} className="document-questions-title">
          The {name} has {plural(open.length, "question", "questions")} for you
        </p>
        {suggested.length > 0 && (
          <fieldset className="field" disabled={saving}>
            <legend>Suggested answers to check ({suggested.length})</legend>
            <p className="hint">
              {suggested.some(fromAPerson)
                ? "Some of these are what you gave for another document, or what was decided in the project; the rest a model suggested from the project's files and documents."
                : "A model suggested these from the project's files and documents."}{" "}
              Check each one; change it, or clear the box if it is wrong. Nothing is recorded until
              you accept.
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
      {answered}
    </>
  );
}

/**
 * The latest version's answered questions, each with the answer the project log holds and a way to
 * change it; nothing while none is answered. Those put back in the form to change are left out.
 */
function SavedAnswers({
  document,
  version,
  changing,
  folded,
  onChange,
}: {
  document: ProjectDocument;
  version: DocumentVersion;
  changing: ReadonlySet<string>;
  folded: boolean;
  onChange: (q: DocumentQuestion) => void;
}) {
  const answers = new Map(document.answers.map((a) => [a.question_id, a]));
  const listed = version.questions.filter((q) => answers.has(q.question_id) && !changing.has(q.question_id));
  if (listed.length === 0) return null;
  return (
    <details className="document-answers" open={!folded}>
      <summary>Answered ({listed.length})</summary>
      <Listed
        questions={listed}
        answers={answers}
        action={(q) => (
          <Button
            variant="quiet"
            size="small"
            icon={Pencil}
            onPress={() => onChange(q)}
            aria-label={`Change your answer to: ${q.question_prompt}`}
          >
            Change
          </Button>
        )}
      />
    </details>
  );
}
