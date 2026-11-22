/**
 * The keyboard shortcut for submitting a multi-line text box, where Enter must stay a new line:
 * Ctrl+Enter, or Cmd+Enter on a Mac. It submits the box's form unless `canSubmit` says not (the
 * submit button's own rules), and is ignored while an input method is composing text.
 */

import type { KeyboardEvent } from "react";

export function submitOnCtrlEnter(event: KeyboardEvent<HTMLTextAreaElement>, canSubmit = true): void {
  if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey) || event.nativeEvent.isComposing) return;
  event.preventDefault();
  if (canSubmit) event.currentTarget.form?.requestSubmit();
}
