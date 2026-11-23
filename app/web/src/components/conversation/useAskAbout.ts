import { type RefObject, useEffect, useRef, useState } from "react";

import { locate } from "../../flow/journey";
import type { FlowPhase, FlowStep, ProcessFlow } from "../../flow/types";
import { type DocumentQuestion, questionTarget } from "../../project/api";
import type { DocumentsRead } from "../../project/drafted";
import { ASK_FOR_FEEDBACK } from "../../project/fairness";
import { ASK_TO_REVIEW_PLAN } from "../../project/facts";
import { documentName } from "../../project/name";
import { homePath, navigate, useLocation } from "../../route";

/** The message that asks for help with a step, in the researcher's voice. */
export function askAboutStep(found: { phase: FlowPhase; step: FlowStep }): string {
  return `Can you help me with this step: ${found.step.label} (phase ${found.phase.number}, ${found.phase.name})?`;
}

/** Whether the address asks for a new conversation: a step of the journey (`?ask=`) or a draft's
 * question (`?question=`) to talk through, asked about from another page. */
export function asksNewConversation(params: URLSearchParams): boolean {
  return params.has("ask") || params.has("question");
}

/** Where an asked-for question goes: the message box's text, the box to focus, and what of the
 * address to keep once the ask is dropped from it. */
export interface AskInto {
  setText(text: string): void;
  box: RefObject<{ focus(): void } | null>;
  keep: { conversation: string | null; run: string | null };
}

/**
 * What the address asks the message box to hold (`?{param}=`), until it is handled: `handle`
 * marks it filled, after which the box is focused and the address drops it so that a reload does
 * not refill. The text is the researcher's to send or change.
 */
export function useAskedInAddress(
  param: string,
  { box, keep }: AskInto,
): { pending: string | null; handle(): void } {
  const asked = new URLSearchParams(useLocation().split("?")[1] ?? "").get(param);
  const [handled, setHandled] = useState<string | null>(null);
  const focus = useFocusOnceDrawn(box);
  useEffect(() => {
    if (!asked || handled !== asked) return;
    focus();
    navigate(homePath(keep), true);
    // Only what was asked, once its text is in the box, is acted on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked, handled]);
  return { pending: asked && handled !== asked ? asked : null, handle: () => setHandled(asked) };
}

/**
 * A step asked about from the journey map (`?ask=`) starts a new conversation by `begin`, with
 * the step's prompt in the message box, unsent. A step the flow does not hold is ignored.
 */
export function useAskAbout(
  flow: { state: "loaded"; flow: ProcessFlow } | { state: string },
  into: AskInto,
  begin: (step: FlowStep) => void,
): void {
  const { pending, handle } = useAskedInAddress("ask", into);
  const loaded = "flow" in flow ? flow.flow : null;
  // Starting a conversation resets what the page holds, so it waits until the render is done.
  useEffect(() => {
    if (!pending || !loaded) return;
    handle();
    const found = locate(loaded, pending);
    if (found) begin(found.step.prompt ? found.step : { ...found.step, prompt: askAboutStep(found) });
    // Only the step asked about is acted on, once, when the flow is there to find it in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, loaded]);
}

/**
 * Focuses `box` when asked, or, if the page has not drawn it yet (the workspace waits for what it
 * reads on load), as soon as a later render has.
 */
function useFocusOnceDrawn(box: RefObject<{ focus(): void } | null>): () => void {
  const waiting = useRef(false);
  useEffect(() => {
    if (!waiting.current || !box.current) return;
    box.current.focus();
    waiting.current = false;
  });
  return () => {
    if (box.current) box.current.focus();
    else waiting.current = true;
  };
}

/**
 * What a project's tab asks for in the address fills the message box, unsent: FAIR feedback from
 * the FAIR feedback tab (`?fair=check`), and a review of the project's plan from the Documents
 * tab (`?dmp=review`). The orchestrator delegates the check or review; the shell does not route.
 */
export function useAskForFairFeedback(into: AskInto): void {
  useAskedMessage("fair", "check", ASK_FOR_FEEDBACK, into);
  useAskedMessage("dmp", "review", ASK_TO_REVIEW_PLAN, into);
}

function useAskedMessage(param: string, value: string, text: string, into: AskInto): void {
  const { pending, handle } = useAskedInAddress(param, into);
  if (pending === value) {
    handle();
    into.setText(text);
  }
}

/** The message that asks for help with a draft's question, in the researcher's voice. */
export function askAboutQuestion(name: string, question: DocumentQuestion): string {
  return (
    `Can you help me answer this question about the ${name}: “${question.question_prompt}” ` +
    `(it fills ${questionTarget(question)})? I'll record my answer on the draft once we've worked it out.`
  );
}

/**
 * A draft's question to talk through (`?question={document_id}/{question_id}`, from its
 * "Talk this through" link) starts a new conversation by `begin`, with the question in the
 * message box, unsent, once the project's documents are read. A question the documents do not
 * ask is ignored. The answer is still recorded on the draft, never here.
 */
export function useAskAboutQuestion(
  documents: DocumentsRead,
  into: AskInto,
  begin: (about: { label: string; prompt: string }) => void,
): void {
  const { pending, handle } = useAskedInAddress("question", into);
  const read = documents.state === "loaded" ? documents.documents : null;
  // Starting a conversation resets what the page holds, so it waits until the render is done.
  useEffect(() => {
    if (!pending || !read) return;
    handle();
    const [documentId, questionId] = pending.split("/");
    const document = read.find((d) => d.document_id === documentId);
    const question = document?.versions
      .flatMap((v) => v.questions)
      .find((q) => q.question_id === questionId);
    if (!document || !question) return;
    const name = documentName(document);
    begin({ label: `a question about the ${name}`, prompt: askAboutQuestion(name, question) });
    // Only the question asked about is acted on, once, when the documents are there to find it in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, read]);
}
