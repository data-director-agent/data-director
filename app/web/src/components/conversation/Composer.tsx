/**
 * The form a message is written and sent from: the message box, what is attached, and the Send
 * button. A file may be dropped on the form. The dialogs that check an attachment first are drawn
 * beside it (`AttachmentDialogs`), since a file may also be attached while answering questions.
 */

import type { FormEvent, RefObject } from "react";

import { SendHorizontal } from "lucide-react";
import { Button } from "../ui/Button";
import { AttachControls } from "./ComposerAttach";
import { MessageField } from "./MessageField";
import type { Attachments } from "./useAttachments";

export function Composer({
  box,
  text,
  onText,
  attachments,
  busy,
  onSend,
}: {
  box: RefObject<HTMLTextAreaElement | null>;
  text: string;
  onText: (text: string) => void;
  attachments: Attachments;
  busy: boolean;
  onSend: () => void;
}) {
  const writing = Boolean(text.trim()) || attachments.carries;
  function submit(event: FormEvent) {
    event.preventDefault();
    onSend();
  }
  return (
    // Dropping a file is a shortcut for the Attach a file button, which keyboard and screen
    // reader users have, so the form's drag listeners need no role of their own.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <form
      onSubmit={submit}
      aria-busy={busy}
      className={attachments.dropping ? "dropping" : undefined}
      onDragOver={attachments.onDragOver}
      onDragLeave={attachments.onDragLeave}
      onDrop={attachments.onDrop}
    >
      <MessageField
        inputRef={box}
        value={text}
        canSend={!busy && writing}
        onChange={onText}
        onPaste={attachments.onPaste}
      />
      <AttachControls attachments={attachments} busy={busy} />
      <Button type="submit" variant="primary" icon={SendHorizontal} isDisabled={!busy && !writing} isPending={busy}>
        {busy ? "Sending…" : "Send"}
      </Button>
    </form>
  );
}
