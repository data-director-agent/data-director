/**
 * The questions a reply asks and the researcher's answers to them (docs/specs/contract.md,
 * `Question`, `ReplyAnswers` and `QuestionAnswer`). The harness checks the answers against the
 * questions; the shell shows the questions one at a time and says the answers in words.
 */

import type { Envelope } from "../run/types";

export interface ChoiceOption {
  option_value: string;
  option_label: string;
  option_help?: string | null;
}

/** How a question is answered: by choosing, on one line, or in several lines. */
export type QuestionKind = "choice" | "short_text" | "long_text";

export interface Question {
  /** The question's identifier within its reply, which its answer names. */
  question_key: string;
  question_prompt: string;
  question_kind: QuestionKind;
  question_help?: string | null;
  /** A choice question's options; absent for a text question. */
  question_options?: ChoiceOption[] | null;
  question_multiple?: boolean | null;
  question_other?: boolean | null;
}

export interface QuestionAnswer {
  answered_key: string;
  /** The values of the options chosen; always empty for a text question. */
  answer_values: string[];
  /** The answer in the researcher's own words. */
  answer_words?: string;
}

export interface ReplyAnswers {
  /** The invocation whose reply asked the questions. */
  answer_to: string;
  /** One answer for each question answered, in the order asked; a skipped question has none. */
  given_answers: QuestionAnswer[];
}

/** The longest answer in the researcher's own words to a short text question, or in place of an
 * option; and to a long text question. The harness holds answers to the same bounds. */
export const SHORT_TEXT_MAX = 200;
export const LONG_TEXT_MAX = 4000;

const KINDS = new Set<string>(["choice", "short_text", "long_text"]);

function isQuestion(value: unknown): value is Question {
  if (typeof value !== "object" || value === null) return false;
  const q = value as Partial<Question>;
  if (typeof q.question_key !== "string" || typeof q.question_prompt !== "string") return false;
  if (!KINDS.has(q.question_kind ?? "")) return false;
  return q.question_kind !== "choice" || Array.isArray(q.question_options);
}

/** The questions a turn's reply asks, in order; empty if it asks none. */
export function replyQuestions(envelope: Envelope): Question[] {
  const payload = envelope.payload;
  if (payload?.schema_class !== "Reply") return [];
  const asked: unknown = payload.reply_questions;
  return Array.isArray(asked) ? asked.filter(isQuestion) : [];
}

/** The reply's own text, without the questions, which history writes after it. */
export function replyOwnText(envelope: Envelope): string | null {
  const payload = envelope.payload;
  if (payload?.schema_class !== "Reply") return null;
  return typeof payload.reply_text === "string" ? payload.reply_text : null;
}

/** One answer in words: the labels chosen, then any answer in the researcher's own words. */
export function answerSaid(question: Question, answer: QuestionAnswer): string {
  const labels = (question.question_options ?? [])
    .filter((o) => answer.answer_values.includes(o.option_value))
    .map((o) => o.option_label);
  const words = answer.answer_words?.trim();
  return [...labels, ...(words ? [words] : [])].join("; ");
}

// Characters that mark up text anywhere in a line, and the marks that open a block at its start.
const INLINE_MARKS = /[\\`*_~[\]|<&]/g;
const BLOCK_MARK = /^[#>+=-]/;
const NUMBERED = /^(\d+)([.)])/;

/** Text the researcher or an agent wrote as plain words, escaped so that Markdown shows it as it
 * was written: a line break stays a line break, and a blank line starts a new paragraph. */
function plainMarkdown(text: string): string {
  return text
    .trim()
    .split(/\n\s*\n/)
    .map((paragraph) =>
      paragraph
        .split("\n")
        .map((line) =>
          line.trim().replace(INLINE_MARKS, "\\$&").replace(BLOCK_MARK, "\\$&").replace(NUMBERED, "$1\\$2"),
        )
        .join("\\\n"),
    )
    .join("\n\n");
}

/** Text as one escaped line, whatever line breaks it held. */
function oneLine(text: string): string {
  return plainMarkdown(text.replace(/\s+/g, " "));
}

/** One answer as Markdown: several options chosen as a list, one as a line, and words as written. */
function answerMarkdown(question: Question, answer: QuestionAnswer): string {
  const labels = (question.question_options ?? [])
    .filter((o) => answer.answer_values.includes(o.option_value))
    .map((o) => oneLine(o.option_label));
  const words = answer.answer_words?.trim();
  if (question.question_kind !== "choice") return plainMarkdown(words ?? "");
  const said = [...labels, ...(words ? [`In my own words: ${oneLine(words)}`] : [])];
  return said.length === 1 ? (said[0] ?? "") : said.map((line) => `- ${line}`).join("\n");
}

/** The answers as the message the researcher sends, in Markdown, so that the agent reads, and the
 * transcript shows, which answer goes with which question: each question asked, in bold, then its
 * answer, or that it was skipped. */
export function answersText(questions: Question[], answers: ReplyAnswers): string {
  return questions
    .map((question) => {
      const answer = answers.given_answers.find((a) => a.answered_key === question.question_key);
      const said = answer ? answerMarkdown(question, answer) : "_Skipped_";
      return `**${oneLine(question.question_prompt)}**\n\n${said}`;
    })
    .join("\n\n");
}
