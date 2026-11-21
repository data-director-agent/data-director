/**
 * The form a message is written and sent from: the message box, what is attached and the dialogs
 * that check an attachment first, and the Send button. A file may be dropped on the form.
 */

import type { FormEvent, RefObject } from "react";

import { SendHorizontal } from "lucide-react";
import { InventoryReviewDialog } from "../inventory/InventoryReviewDialog";
import { Button } from "../ui/Button";
import { ComposerAttach } from "./ComposerAttach";
import { DocumentReviewDialog } from "./DocumentReviewDialog";
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
    <>
      {/* Dropping a file is a shortcut for the Attach a file button, which keyboard and
          screen reader users have, so the form's drag listeners need no role of their own. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
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
        <ComposerAttach
          attached={attachments.inventory}
          attachedDocument={attachments.document}
          documents={attachments.documents}
          busy={busy}
          onAttachFiles={(files) => void attachments.attachFiles(files)}
          onRemoveInventory={attachments.removeInventory}
          onRemoveDocument={attachments.removeDocument}
        />
        <InventoryReviewDialog
          pending={attachments.pendingInventory}
          onAttach={attachments.confirmInventory}
          onDiscard={attachments.discardInventory}
        />
        <DocumentReviewDialog
          pending={attachments.pendingDocument}
          replaces={attachments.document?.name}
          onAttach={attachments.confirmDocument}
          onDiscard={attachments.discardDocument}
        />
        {/* Said in the live region when it is set, so not live here. */}
        {attachments.notice && <p className="callout">{attachments.notice}</p>}
        {attachments.error && (
          <p role="alert" className="callout status-danger">
            {attachments.error}
          </p>
        )}
        <Button
          type="submit"
          variant="primary"
          icon={SendHorizontal}
          isDisabled={!busy && !writing}
          isPending={busy}
        >
          {busy ? "Sending…" : "Send"}
        </Button>
      </form>
    </>
  );
}
