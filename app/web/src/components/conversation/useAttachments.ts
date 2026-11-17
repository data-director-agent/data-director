/**
 * What a message carries besides its text: one `dd-inventory` file and one supporting document,
 * chosen with the Attach button, dropped on the form or (an inventory) pasted into the message
 * box. Each is first opened to be checked and is attached, as a chip, only when the researcher
 * confirms (#443, #472, docs/specs/app.md). Focus goes back to the message box once a dialog
 * closes or a chip goes.
 */

import { type ClipboardEvent, type DragEvent, type RefObject, useState } from "react";

import {
  type AttachedDocument,
  NotADocument,
  isDocumentName,
  readDocument,
} from "../../conversation/documentation";
import {
  type AttachedInventory,
  NotAnInventory,
  looksLikeInventory,
  readInventory,
} from "../../conversation/inventory";
import { errorMessage } from "../../run/api";

/** What a message carries besides its text. */
export interface Carried {
  inventory: AttachedInventory | null;
  document: AttachedDocument | null;
}

export interface Attachments extends Carried {
  /** Whether the next message carries an inventory or a document. */
  carries: boolean;
  /** An inventory read from a file and being checked, not yet attached (#472). */
  pendingInventory: AttachedInventory | null;
  /** A document read from a file and being checked, not yet attached. */
  pendingDocument: AttachedDocument | null;
  /** Why the last file could not be attached. */
  error: string | null;
  /** Whether a file is being dragged over the form. */
  dropping: boolean;
  attachFile(file: File | undefined): Promise<void>;
  attachFromDialog(file: File): Promise<void>;
  confirmInventory(checked: AttachedInventory): void;
  discardInventory(): void;
  confirmDocument(checked: AttachedDocument): void;
  discardDocument(): void;
  removeInventory(): void;
  removeDocument(): void;
  onPaste(event: ClipboardEvent<HTMLTextAreaElement>): void;
  onDragOver(event: DragEvent<HTMLFormElement>): void;
  onDragLeave(): void;
  onDrop(event: DragEvent<HTMLFormElement>): void;
  /** Puts `carried` on the next message, as when a send that failed gives it back. */
  restore(carried: Carried): void;
  clearError(): void;
}

function focusLater(box: RefObject<HTMLTextAreaElement | null>) {
  requestAnimationFrame(() => box.current?.focus());
}

export function useAttachments(
  box: RefObject<HTMLTextAreaElement | null>,
  announce: (said: string) => void,
): Attachments {
  const [inventory, setInventory] = useState<AttachedInventory | null>(null);
  const [pendingInventory, setPendingInventory] = useState<AttachedInventory | null>(null);
  const [document, setDocument] = useState<AttachedDocument | null>(null);
  const [pendingDocument, setPendingDocument] = useState<AttachedDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);

  /** Reads `content` as an inventory and opens it to be checked, or says why it cannot. */
  function attachInventory(content: string, name: string | null) {
    try {
      setPendingInventory(readInventory(content, name));
      setError(null);
    } catch (e) {
      setError(e instanceof NotAnInventory ? e.message : errorMessage(e));
    }
  }

  /** Reads a text or Markdown file as a document and opens it to be checked, or says why not. */
  function attachDocument(content: string, name: string) {
    try {
      setPendingDocument(readDocument(content, name));
      setError(null);
    } catch (e) {
      setError(e instanceof NotADocument ? e.message : errorMessage(e));
    }
  }

  /** A file chosen or dropped: a document by its name, otherwise read as an inventory. */
  async function attachFile(file: File | undefined) {
    if (!file) return;
    try {
      const content = await file.text();
      if (isDocumentName(file.name)) attachDocument(content, file.name);
      else attachInventory(content, file.name);
    } catch (e) {
      setError(`Data Director could not read ${file.name}: ${errorMessage(e)}`);
    }
  }

  /**
   * A file chosen at the end of the Make an inventory dialog. Once it is attached the dialog's
   * button gives way to the chip, so focus goes to the message box rather than nowhere; if it is
   * not an inventory, the dialog's button stays and takes the focus back.
   */
  async function attachFromDialog(file: File) {
    await attachFile(file);
    requestAnimationFrame(() => {
      const active = globalThis.document.activeElement;
      if (!active || active === globalThis.document.body) box.current?.focus();
    });
  }

  /** The checked inventory, without what the researcher left out, becomes the chip. */
  function confirmInventory(checked: AttachedInventory) {
    setPendingInventory(null);
    setInventory(checked);
    announce("Inventory attached.");
    focusLater(box);
  }

  function discardInventory() {
    setPendingInventory(null);
    announce("Inventory not attached.");
    focusLater(box);
  }

  function confirmDocument(checked: AttachedDocument) {
    setPendingDocument(null);
    setDocument(checked);
    announce(`${checked.name} attached.`);
    focusLater(box);
  }

  function discardDocument() {
    setPendingDocument(null);
    announce("Document not attached.");
    focusLater(box);
  }

  function removeDocument() {
    const name = document?.name ?? "Document";
    setDocument(null);
    announce(`${name} removed.`);
    box.current?.focus();
  }

  function removeInventory() {
    setInventory(null);
    announce("Inventory removed.");
    box.current?.focus();
  }

  // A whole inventory pasted into the box becomes a chip, not text (#443).
  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = event.clipboardData.getData("text");
    if (!looksLikeInventory(pasted)) return;
    event.preventDefault();
    attachInventory(pasted, null);
  }

  function onDragOver(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(true);
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(false);
    void attachFile(event.dataTransfer.files[0]);
  }

  function restore(carried: Carried) {
    setInventory(carried.inventory);
    setDocument(carried.document);
  }

  return {
    inventory,
    document,
    carries: Boolean(inventory || document),
    pendingInventory,
    pendingDocument,
    error,
    dropping,
    attachFile,
    attachFromDialog,
    confirmInventory,
    discardInventory,
    confirmDocument,
    discardDocument,
    removeInventory,
    removeDocument,
    onPaste,
    onDragOver,
    onDragLeave: () => setDropping(false),
    onDrop,
    restore,
    clearError: () => setError(null),
  };
}
