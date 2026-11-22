/** The message box: a labelled text area that Ctrl+Enter (Cmd+Enter on a Mac) sends from. */

import type { ClipboardEvent, Ref } from "react";

import { submitOnCtrlEnter } from "./submitShortcut";

export function MessageField({
  inputRef,
  value,
  canSend,
  onChange,
  onPaste,
}: {
  inputRef: Ref<HTMLTextAreaElement>;
  value: string;
  /** Whether Ctrl+Enter may send now; the Send button's rules still apply. */
  canSend: boolean;
  onChange: (value: string) => void;
  onPaste: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
}) {
  return (
    <div className="field">
      <label htmlFor="message">What would you like to do?</label>
      <textarea
        id="message"
        ref={inputRef}
        rows={3}
        aria-describedby="message-hint"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onPaste={onPaste}
        onKeyDown={(e) => submitOnCtrlEnter(e, canSend)}
      />
      <p id="message-hint" className="hint">
        Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on a Mac) to send.
      </p>
    </div>
  );
}
