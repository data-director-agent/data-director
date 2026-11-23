/**
 * An answer that is a list of values (`answer_kind` `list`), such as the values of a data dictionary
 * column that mean a value is missing. The person writes one value on each line; what is recorded
 * is a JSON array of strings, the form of a Frictionless Table Schema `missingValues`
 * (https://datapackage.org/standard/table-schema/), which the drafter keeps as it is
 * (docs/specs/drafting.md).
 */

import type { DocumentQuestion } from "./api";

/**
 * What a box holds when the person says no value means missing: the standard's default, in which
 * only an empty cell is missing, written as the array that says so.
 */
export const NO_VALUES = '[""]';

/** Whether a question is answered with a list of values. */
export function isList(q: DocumentQuestion): boolean {
  return q.answer_kind === "list";
}

/** The values a box holds, one on each line, trimmed, with blank lines and repeats left out. */
export function valuesIn(text: string): string[] {
  return [...new Set(text.split("\n").map((line) => line.trim()).filter((line) => line !== ""))];
}

/** The answer a box's text records: the JSON array of its values, or "" when it holds none. */
export function listAnswer(text: string): string {
  if (text.trim() === NO_VALUES) return NO_VALUES;
  const values = valuesIn(text);
  return values.length === 0 ? "" : JSON.stringify(values);
}

/**
 * What a box holds for an answer already recorded or suggested: a JSON array of strings as one
 * value on each line, and any other text, a note an earlier answer was written as, as it is.
 */
export function listText(answer: string): string {
  try {
    const loaded: unknown = JSON.parse(answer);
    if (Array.isArray(loaded) && loaded.every((v) => typeof v === "string")) {
      return answer.trim() === NO_VALUES ? NO_VALUES : loaded.join("\n");
    }
  } catch {
    // Not JSON: the person's own words.
  }
  return answer;
}

/** What to say about a box's lines: a line that looks like several values, or like a note. */
export function listWarnings(text: string): string[] {
  const lines = valuesIn(text);
  const warnings: string[] = [];
  if (lines.some((line) => /[,;]/.test(line))) {
    warnings.push(
      "A line holds a comma or semicolon. Put each value on its own line, unless it is one value.",
    );
  }
  if (lines.some((line) => /[()[\]:]|\.\s/.test(line))) {
    warnings.push("A line reads like a note. Give each value exactly as it is written in the file.");
  }
  return warnings;
}
