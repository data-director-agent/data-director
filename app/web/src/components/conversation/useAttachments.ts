/**
 * What a message carries besides its text: one `dd-inventory` file and one supporting document,
 * chosen with the Attach button, dropped on the form or (an inventory) pasted into the message
 * box. Each is first opened to be checked and is attached, as a chip, only when the researcher
 * confirms (#443, #472, docs/specs/app.md). Focus goes back to the message box once a dialog
 * closes or a chip goes.
 *
 * Files are attached one at a time: of several chosen or dropped together, the first is opened
 * and the rest are named, on the form and in the live region, as not attached. Attaching a
 * document or an inventory where one is already attached replaces it, and says so (#1170).
 */

import { type ClipboardEvent, type DragEvent, type RefObject, useState } from "react";

import {
  type AttachedDocument,
  NotADocument,
  isDocumentName,
  readDocument,
  readSource,
  sourceMediaType,
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
  /** Whether the profile lets a document be attached; if not, only an inventory may be. */
  documents: boolean;
  /** Whether the next message carries an inventory or a document. */
  carries: boolean;
  /** An inventory read from a file and being checked, not yet attached (#472). */
  pendingInventory: AttachedInventory | null;
  /** A document read from a file and being checked, not yet attached. */
  pendingDocument: AttachedDocument | null;
  /** Why the last file could not be attached. */
  error: string | null;
  /** Which files chosen or dropped with the one opened were not attached (#1170). */
  notice: string | null;
  /** Whether a file is being dragged over the form. */
  dropping: boolean;
  attachFile(file: File | undefined): Promise<void>;
  /** Opens the first of `files` to be checked and says which of the others were not attached. */
  attachFiles(files: FileList | readonly File[] | null): Promise<void>;
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

function focusLater(box: RefObject<{ focus(): void } | null>) {
  requestAnimationFrame(() => box.current?.focus());
}

/** Why a document cannot be attached where the profile refuses them (docs/specs/projects.md). */
export const DOCUMENTS_REFUSED =
  "This deployment does not keep attached documents: its profile refuses them. Give what the " +
  "document says in your message instead.";

/** Names in a sentence: "a", "a and b", "a, b and c". */
function listed(names: readonly string[]): string {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

/** What is said when files beyond the first are chosen or dropped together (#1170). */
export function notAttached(opened: string, left: readonly string[]): string {
  const one = left.length === 1;
  return (
    `Only ${opened} was opened. ${listed(left)} ${one ? "was" : "were"} not attached: files ` +
    "are attached one at a time, and a message carries one inventory and one document. " +
    `Attach ${one ? "it" : "each"} on its own.`
  );
}

export function useAttachments(
  box: RefObject<{ focus(): void } | null>,
  announce: (said: string) => void,
  documents = true,
): Attachments {
  const [inventory, setInventory] = useState<AttachedInventory | null>(null);
  const [pendingInventory, setPendingInventory] = useState<AttachedInventory | null>(null);
  const [document, setDocument] = useState<AttachedDocument | null>(null);
  const [pendingDocument, setPendingDocument] = useState<AttachedDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
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
      const source = sourceMediaType(file.name);
      if (!isDocumentName(file.name)) attachInventory(await file.text(), file.name);
      else if (!documents) setError(DOCUMENTS_REFUSED);
      else if (source === null) attachDocument(await file.text(), file.name);
      else {
        // A Word document or PDF is read on the server, inside the deployment (#961).
        setPendingDocument(await readSource(file, source));
        setError(null);
      }
    } catch (e) {
      setError(
        e instanceof NotADocument
          ? e.message
          : `Data Director could not read ${file.name}: ${errorMessage(e)}`,
      );
    }
  }

  /** Files chosen or dropped together: only the first is opened, and the rest are named. */
  async function attachFiles(files: FileList | readonly File[] | null) {
    const [first, ...rest] = Array.from(files ?? []);
    const left = first && rest.length ? notAttached(first.name, rest.map((file) => file.name)) : null;
    setNotice(left);
    if (left) announce(left);
    await attachFile(first);
  }

  /** The checked inventory, without what the researcher left out, becomes the chip. */
  function confirmInventory(checked: AttachedInventory) {
    setPendingInventory(null);
    setInventory(checked);
    announce(inventory ? "Inventory attached in place of the one attached before." : "Inventory attached.");
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
    announce(
      document ? `${checked.name} attached in place of ${document.name}.` : `${checked.name} attached.`,
    );
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
    void attachFiles(event.dataTransfer.files);
  }

  function restore(carried: Carried) {
    setInventory(carried.inventory);
    setDocument(carried.document);
  }

  return {
    inventory,
    document,
    documents,
    carries: Boolean(inventory || document),
    pendingInventory,
    pendingDocument,
    error,
    notice,
    dropping,
    attachFile,
    attachFiles,
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
    clearError: () => {
      setError(null);
      setNotice(null);
    },
  };
}
