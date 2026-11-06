/**
 * A reply's choice question and the researcher's answer to it (docs/specs/contract.md,
 * `ChoiceQuestion` and `ChoiceAnswer`). The harness checks an answer against its question; the
 * shell only shows the question and says the answer in words.
 */

import type { Envelope } from "../run/types";

export interface ChoiceOption {
  option_value: string;
  option_label: string;
  option_help?: string | null;
}

export interface ChoiceQuestion {
  question_prompt: string;
  question_options: ChoiceOption[];
  question_multiple?: boolean | null;
  question_other?: boolean | null;
}

export interface ChoiceAnswer {
  /** The invocation whose reply asked the question. */
  answer_to: string;
  answer_values: string[];
  answer_other?: string;
}

/** The choice question a turn's reply asks, or null. */
export function replyQuestion(envelope: Envelope): ChoiceQuestion | null {
  const payload = envelope.payload;
  if (payload?.schema_class !== "Reply") return null;
  const question = payload.reply_question as ChoiceQuestion | null | undefined;
  return question && Array.isArray(question.question_options) ? question : null;
}

/** The reply's own text, without the question, which history writes after it. */
export function replyOwnText(envelope: Envelope): string | null {
  const payload = envelope.payload;
  if (payload?.schema_class !== "Reply") return null;
  return typeof payload.reply_text === "string" ? payload.reply_text : null;
}

/** The answer in words, as the message the researcher sends: the labels chosen, then any answer
 * in their own words. */
export function answerText(question: ChoiceQuestion, answer: ChoiceAnswer): string {
  const labels = question.question_options
    .filter((o) => answer.answer_values.includes(o.option_value))
    .map((o) => o.option_label);
  const other = answer.answer_other?.trim();
  return [...labels, ...(other ? [other] : [])].join("; ");
}
