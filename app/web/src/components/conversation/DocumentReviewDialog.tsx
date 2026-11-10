/**
 * The check a supporting document goes through before it is attached. Whether it was chosen
 * with the Attach button or dropped on the form, the researcher sees its text and what will
 * become of it, and attaches it only by pressing **Attach this document**. Until then nothing is
 * attached, so nothing can be sent or recorded; closing the dialog any other way discards it.
 * That documentation goes to a hosted model only where the deployment allows it is the Projects
 * spec's rule, stated here so that the researcher knows it when deciding; the dialog holds no
 * policy.
 */

import "./DocumentReviewDialog.css";

import { Check } from "lucide-react";

import { type AttachedDocument, DOCUMENT_GUIDE, describeSize } from "../../conversation/documentation";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";

export function DocumentReviewDialog({
  pending,
  onAttach,
  onDiscard,
}: {
  /** The document read from the file, not yet attached; null when there is none to check. */
  pending: AttachedDocument | null;
  onAttach: (attached: AttachedDocument) => void;
  onDiscard: () => void;
}) {
  return (
    <ModalDialog
      title="Check the document before attaching it"
      isOpen={pending !== null}
      onOpenChange={(open) => {
        if (!open) onDiscard();
      }}
      footer={
        pending && (
          <>
            <Button onPress={onDiscard}>Cancel</Button>
            <Button variant="primary" icon={Check} onPress={() => onAttach(pending)}>
              Attach this document
            </Button>
          </>
        )
      }
    >
      {pending && (
        <>
          <div className="callout">
            <p>
              <strong>{pending.name}</strong> ({describeSize(pending.size)}) will be stored in the
              project, where anyone working on the project can read it. Agents are told its
              name, type and size, not its text. Should an agent be given its text in future, it
              will go to an AI model hosted outside your institution only if this deployment
              allows that.
            </p>
            <p>
              Attach documents <em>about</em> your data, such as a protocol or a codebook, never
              the data themselves, and nothing that identifies a person.{" "}
              <a href={DOCUMENT_GUIDE}>What to attach</a>
            </p>
          </div>
          <h3 className="document-review-heading">What it says</h3>
          {/* Scrollable, so it must be reachable by keyboard. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <pre className="document-review-text" tabIndex={0} aria-label={`The text of ${pending.name}`}>
            {pending.text}
          </pre>
        </>
      )}
    </ModalDialog>
  );
}
