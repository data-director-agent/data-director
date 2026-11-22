/**
 * What the researcher has typed in a draft's question form and not yet saved (`DocumentQuestions`).
 * The text lives only in the page until it is saved, so each box says when it holds a change not
 * saved, and leaving or reloading the page asks first while any does.
 *
 * An answered question leaves the form; "Change" puts it back, its box holding the saved answer,
 * and saving records a new answer, which stands in place of the old (docs/specs/drafting.md).
 */

import { useEffect, useState } from "react";

import {
  type DocumentQuestion,
  type DocumentVersion,
  type ProjectDocument,
  openQuestions,
} from "../../project/api";

/** A question's suggested answer, or "" when it has none. */
export function suggestion(q: DocumentQuestion): string {
  return q.suggested_answer ?? "";
}

function without(record: Record<string, string>, ids: readonly string[]): Record<string, string> {
  return Object.fromEntries(Object.entries(record).filter(([id]) => !ids.includes(id)));
}

export interface AnswerDrafts {
  /** The questions in the form: those put back to change first, then those still open. */
  open: DocumentQuestion[];
  /** The questions put back to change an answer already saved. */
  changing: ReadonlySet<string>;
  /** What a question's box holds. */
  value(q: DocumentQuestion): string;
  /** Whether a question's box holds a change not saved. */
  unsaved(q: DocumentQuestion): boolean;
  type(q: DocumentQuestion, text: string): void;
  /** Puts an answered question back in the form, its box holding the saved answer. */
  change(q: DocumentQuestion): void;
  /** Takes an answered question out of the form again, its saved answer kept. */
  keep(q: DocumentQuestion): void;
  /** Forgets what was typed for the questions whose answers were just saved. */
  saved(questionIds: readonly string[]): void;
}

export function useAnswerDrafts(document: ProjectDocument, version: DocumentVersion): AnswerDrafts {
  // What the person has typed or changed; a box not touched holds its suggestion or saved answer.
  const [words, setWords] = useState<Record<string, string>>({});
  const [changing, setChanging] = useState<ReadonlySet<string>>(new Set());
  const answers = new Map(document.answers.map((a) => [a.question_id, a.answer_text]));

  const start = (q: DocumentQuestion) =>
    (changing.has(q.question_id) ? answers.get(q.question_id) : undefined) ?? suggestion(q);
  const value = (q: DocumentQuestion) => words[q.question_id] ?? start(q);
  const unsaved = (q: DocumentQuestion) => {
    const typed = words[q.question_id];
    return typed !== undefined && typed !== start(q);
  };
  const put = version.questions.filter((q) => changing.has(q.question_id) && answers.has(q.question_id));
  const open = [...put, ...openQuestions(document, version)];
  const dirty = open.some(unsaved);

  useEffect(() => {
    if (!dirty) return;
    // The browser asks before the page is left or reloaded; the words are its own.
    const ask = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [dirty]);

  return {
    open,
    changing,
    value,
    unsaved,
    type: (q, text) => setWords((was) => ({ ...was, [q.question_id]: text })),
    change: (q) => setChanging((was) => new Set([...was, q.question_id])),
    keep: (q) => {
      setChanging((was) => new Set([...was].filter((id) => id !== q.question_id)));
      setWords((was) => without(was, [q.question_id]));
    },
    saved: (ids) => {
      setChanging((was) => new Set([...was].filter((id) => !ids.includes(id))));
      setWords((was) => without(was, ids));
    },
  };
}
