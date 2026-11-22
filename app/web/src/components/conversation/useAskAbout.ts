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

/**
 * A step asked about from the journey map (`?ask=`) fills the message box, unsent, so that the
 * researcher's own word starts the turn; the address then drops it so a reload does not refill.
 */
export function useAskAbout(
  flow: { state: "loaded"; flow: ProcessFlow } | { state: string },
  setText: (text: string) => void,
  box: RefObject<HTMLTextAreaElement | null>,
  keep: { conversation: string | null; run: string | null },
): void {
  const askAbout = new URLSearchParams(useLocation().split("?")[1] ?? "").get("ask");
  const [askedAbout, setAskedAbout] = useState<string | null>(null);
  if (askAbout && "flow" in flow && askedAbout !== askAbout) {
    setAskedAbout(askAbout);
    const found = locate(flow.flow, askAbout);
    if (found) {
      setText(askAboutStep(found));
    }
  }
  const focus = useFocusOnceDrawn(box);
  useEffect(() => {
    if (!askAbout || askedAbout !== askAbout) return;
    focus();
    navigate(homePath(keep), true);
    // Only the step asked about, once its text is in the box, is acted on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askAbout, askedAbout]);
}

/**
 * Focuses `box` when asked, or, if the page has not drawn it yet (the workspace waits for what it
 * reads on load), as soon as a later render has.
 */
function useFocusOnceDrawn(box: RefObject<HTMLTextAreaElement | null>): () => void {
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
 * box, unsent, so that the researcher's own word starts the turn; the address then drops it so a
 * reload does not refill. The orchestrator delegates the check; the shell does not route.
 */
export function useAskForFairFeedback(
  setText: (text: string) => void,
  box: RefObject<HTMLTextAreaElement | null>,
  keep: { conversation: string | null; run: string | null },
): void {
  const asked = new URLSearchParams(useLocation().split("?")[1] ?? "").get("fair") === "check";
  const [handled, setHandled] = useState(false);
  if (asked && !handled) {
    setHandled(true);
    setText(ASK_FOR_FEEDBACK);
  }
  const focus = useFocusOnceDrawn(box);
  useEffect(() => {
    if (!asked || !handled) return;
    focus();
    navigate(homePath(keep), true);
    // Only the request, once its text is in the box, is acted on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked, handled]);
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
 * project's documents are read; the address then drops it so a reload does not refill. A question
 * the documents do not ask is ignored. The answer is still recorded on the draft, never here.
 */
export function useAskAboutQuestion(
  documents: DocumentsRead,
  setText: (text: string) => void,
  box: RefObject<HTMLTextAreaElement | null>,
  keep: { conversation: string | null; run: string | null },
): void {
  const asked = new URLSearchParams(useLocation().split("?")[1] ?? "").get("question");
  const [handled, setHandled] = useState<string | null>(null);
  if (asked && documents.state === "loaded" && handled !== asked) {
    setHandled(asked);
    const [documentId, questionId] = asked.split("/");
    const document = documents.documents.find((d) => d.document_id === documentId);
    const question = document?.versions
      .flatMap((v) => v.questions)
      .find((q) => q.question_id === questionId);
    if (document && question) setText(askAboutQuestion(documentName(document), question));
  }
  const focus = useFocusOnceDrawn(box);
  useEffect(() => {
    if (!asked || handled !== asked) return;
    focus();
    navigate(homePath(keep), true);
    // Only the question asked about, once its text is in the box, is acted on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked, handled]);
}
