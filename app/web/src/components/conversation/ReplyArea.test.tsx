import { act, renderHook } from "@testing-library/react";

import type { Question } from "../../conversation/question";
import { type Asking, useReplyMode } from "./ReplyArea";

const QUESTION: Question = {
  question_key: "entry",
  question_kind: "choice",
  question_prompt: "Where are you with your research data?",
  question_options: [{ option_value: "1", option_label: "Planning" }],
};
const asking = (askedBy: string): Asking => ({ askedBy, askedByName: "orchestrator", questions: [QUESTION] });

describe("useReplyMode", () => {
  it("shows the message box when nothing is asked", () => {
    const { result } = renderHook(() => useReplyMode(null));
    expect(result.current.words).toBe(true);
  });

  it("shows the questions when a turn asks, and again when a new turn asks", () => {
    const { result, rerender } = renderHook(({ a }) => useReplyMode(a), {
      initialProps: { a: asking("t1") as Asking | null },
    });
    expect(result.current.words).toBe(false);
    act(() => result.current.setWords(true));
    expect(result.current.words).toBe(true);
    rerender({ a: asking("t1") });
    expect(result.current.words).toBe(true);
    rerender({ a: asking("t2") });
    expect(result.current.words).toBe(false);
  });
});
