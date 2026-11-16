import { type RefObject, useEffect, useState } from "react";

import { locate } from "../../flow/journey";
import type { ProcessFlow } from "../../flow/types";
import { homePath, navigate, useLocation } from "../../route";

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
      setText(
        `Can you help me with this step: ${found.step.label} (phase ${found.phase.number}, ${found.phase.name})?`,
      );
    }
  }
  useEffect(() => {
    if (!askAbout || askedAbout !== askAbout) return;
    box.current?.focus();
    navigate(homePath(keep), true);
    // Only the step asked about, once its text is in the box, is acted on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askAbout, askedAbout]);
}
