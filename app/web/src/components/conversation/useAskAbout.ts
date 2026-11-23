import { type RefObject, useEffect, useRef, useState } from "react";

import { locate } from "../../flow/journey";
import type { FlowPhase, FlowStep, ProcessFlow } from "../../flow/types";
import { type DocumentQuestion, questionTarget } from "../../project/api";
import type { DocumentsRead } from "../../project/drafted";
import { ASK_FOR_FEEDBACK } from "../../project/fairness";
import { documentName } from "../../project/name";
import { homePath, navigate, useLocation } from "../../route";

/** The message that asks for help with a step, in the researcher's voice. */
export function askAboutStep(found: { phase: FlowPhase; step: FlowStep }): string {
  return `Can you help me with this step: ${found.step.label} (phase ${found.phase.number}, ${found.phase.name})?`;
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
 * FAIR feedback asked for from the project's FAIR feedback tab (`?fair=check`) fills the message
 * box, unsent. The orchestrator delegates the check; the shell does not route.
 */
export function useAskForFairFeedback(
  into: AskInto,
): void {
  const { pending, handle } = useAskedInAddress("fair", into);
  if (pending === "check") {
    handle();
    into.setText(ASK_FOR_FEEDBACK);
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
 * "Talk this through" link) fills the message box of a new conversation, unsent, once the
 * project's documents are read. A question the documents do not ask is ignored. The answer is
 * still recorded on the draft, never here.
 */
export function useAskAboutQuestion(
  documents: DocumentsRead,
  into: AskInto,
): void {
  const { pending, handle } = useAskedInAddress("question", into);
  if (pending && documents.state === "loaded") {
    handle();
    const [documentId, questionId] = pending.split("/");
    const document = documents.documents.find((d) => d.document_id === documentId);
    const question = document?.versions
      .flatMap((v) => v.questions)
      .find((q) => q.question_id === questionId);
    if (document && question) into.setText(askAboutQuestion(documentName(document), question));
  }
}
