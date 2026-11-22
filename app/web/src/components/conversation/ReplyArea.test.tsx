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
  const render = (a: Asking | null, intakeOpen: boolean) =>
    renderHook(({ a, intakeOpen }) => useReplyMode(a, intakeOpen), {
      initialProps: { a, intakeOpen },
    });

  it("shows the message box when nothing is asked", () => {
    const { result } = render(null, false);
    expect(result.current.mode).toBe("words");
  });

  it("shows the questions when a turn asks, and again when a new turn asks", () => {
    const { result, rerender } = render(asking("t1"), false);
    expect(result.current.mode).toBe("questions");
    act(() => result.current.setMode("words"));
    expect(result.current.mode).toBe("words");
    rerender({ a: asking("t1"), intakeOpen: false });
    expect(result.current.mode).toBe("words");
    rerender({ a: asking("t2"), intakeOpen: false });
    expect(result.current.mode).toBe("questions");
  });

  it("shows the open intake in the box's place, and keeps the box once chosen", () => {
    const { result, rerender } = render(null, true);
    expect(result.current.mode).toBe("intake");
    act(() => result.current.setMode("words"));
    // A turn sent from the box that asks nothing leaves the box shown.
    rerender({ a: null, intakeOpen: true });
    expect(result.current.mode).toBe("words");
    act(() => result.current.setMode("intake"));
    expect(result.current.mode).toBe("intake");
  });

  it("puts a reply's questions before the open intake", () => {
    const { result, rerender } = render(null, true);
    rerender({ a: asking("t1"), intakeOpen: true });
    expect(result.current.mode).toBe("questions");
    act(() => result.current.setMode("intake"));
    expect(result.current.mode).toBe("intake");
    // Once the questions are answered the researcher is replying, so the box shows.
    rerender({ a: null, intakeOpen: true });
    expect(result.current.mode).toBe("words");
  });

  it("shows the intake when it opens again, and the box once it closes", () => {
    const { result, rerender } = render(null, false);
    rerender({ a: null, intakeOpen: true });
    expect(result.current.mode).toBe("intake");
    rerender({ a: null, intakeOpen: false });
    expect(result.current.mode).toBe("words");
  });

  it("never shows a way that is not open", () => {
    const { result } = render(null, false);
    act(() => result.current.setMode("intake"));
    expect(result.current.mode).toBe("words");
  });
});
