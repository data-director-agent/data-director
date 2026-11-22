/**
 * What checks a file before it is attached, and what attaching said: the dialogs that open an
 * inventory or a document to be checked (#472), and the notice or error that attaching left. They
 * are drawn once beside whichever way of replying is shown (`ReplyArea`), so that a file attached
 * while answering questions is checked as one attached to a message is.
 */

import { InventoryReviewDialog } from "../inventory/InventoryReviewDialog";
import { DocumentReviewDialog } from "./DocumentReviewDialog";
import type { DocumentReaders } from "../../conversation/documentation";
import type { Attachments } from "./useAttachments";

export function AttachmentDialogs({
  attachments,
  readers,
}: {
  attachments: Attachments;
  /** Who reads an attached document's text, said when one is attached (#1326). */
  readers: DocumentReaders;
}) {
  return (
    <>
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
        readers={readers}
      />
      {/* Said in the live region when it is set, so not live here. */}
      {attachments.notice && <p className="callout">{attachments.notice}</p>}
      {attachments.error && (
        <p role="alert" className="callout status-danger">
          {attachments.error}
        </p>
      )}
    </>
  );
}
