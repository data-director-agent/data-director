import type { DocumentQuestion } from "./api";
import { NO_VALUES, isList, listAnswer, listText, listWarnings, valuesIn } from "./listAnswer";

const question = (answer_kind?: "text" | "list"): DocumentQuestion => ({
  question_id: "q-0000000000000001",
  question_prompt: "Which values mean missing?",
  ...(answer_kind ? { answer_kind } : {}),
});

describe("a list answer", () => {
  it("is asked of a question that says so, and no other", () => {
    expect(isList(question("list"))).toBe(true);
    expect(isList(question("text"))).toBe(false);
    expect(isList(question())).toBe(false);
  });

  it("records one value on each line as a JSON array, trimmed and without blanks or repeats", () => {
    expect(valuesIn(" -99 \n\nNA\n-99\n")).toEqual(["-99", "NA"]);
    expect(listAnswer(" -99 \n\nNA\n-99\n")).toBe('["-99","NA"]');
    expect(listAnswer("a, b")).toBe('["a, b"]');
    expect(listAnswer("  \n ")).toBe("");
  });

  it("records no value meaning missing as the standard's default, an empty cell only", () => {
    expect(listAnswer(NO_VALUES)).toBe('[""]');
    expect(JSON.parse(listAnswer(NO_VALUES))).toEqual([""]);
  });

  it("puts a recorded or suggested answer back as lines, and a note as it was written", () => {
    expect(listText('["-99","NA"]')).toBe("-99\nNA");
    expect(listText(listAnswer("-99\nNA"))).toBe("-99\nNA");
    expect(listText('[""]')).toBe(NO_VALUES);
    expect(listText("-999 (sensor off)")).toBe("-999 (sensor off)");
    expect(listText('["a", 1]')).toBe('["a", 1]');
  });

  it("warns of a line that reads like several values, or like a note, and not of a number", () => {
    expect(listWarnings("-99\nNA\n85.0")).toEqual([]);
    expect(listWarnings("-99, NA")).toHaveLength(1);
    expect(listWarnings("-999 (sensor off)")).toHaveLength(1);
    expect(listWarnings("-99, NA (none)")).toHaveLength(2);
  });
});
