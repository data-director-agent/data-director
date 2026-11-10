/**
 * The check an inventory goes through before it is attached (#472). Whatever way it came (the
 * Attach button, a drop, a paste or Make an inventory), the researcher sees everything it holds in
 * the inventory editor, may leave out files, folders and columns and say what the command cannot
 * know, and attaches it only by pressing **Attach this inventory**. Until then nothing is attached, so nothing can be sent or recorded. Closing the
 * dialog any other way discards it. The dialog lays out what `@data-director/inventory` says and
 * holds no policy; that only `inventory` content goes to a hosted model by default is the
 * Projects spec's rule, stated here so that the researcher knows it when deciding.
 */

import { Check } from "lucide-react";
import { useState } from "react";

import { INVENTORY_GUIDE, withEdits, type AttachedInventory } from "../../conversation/inventory";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { startHistory, type EditHistory } from "./history";
import { InventoryEditor } from "./InventoryEditor";

export function InventoryReviewDialog({
  pending,
  onAttach,
  onDiscard,
}: {
  /** The inventory read from the file, not yet attached; null when there is none to check. */
  pending: AttachedInventory | null;
  onAttach: (attached: AttachedInventory) => void;
  onDiscard: () => void;
}) {
  // A new inventory starts with nothing changed.
  const [choice, setChoice] = useState<{ for: AttachedInventory | null; history: EditHistory }>(
    () => ({ for: pending, history: startHistory() }),
  );
  if (choice.for !== pending) setChoice({ for: pending, history: startHistory() });
  const history = choice.for === pending ? choice.history : startHistory();
  return (
    <ModalDialog
      title="Check the inventory before attaching it"
      isOpen={pending !== null}
      onOpenChange={(open) => {
        if (!open) onDiscard();
      }}
      footer={
        pending && (
          <>
            <Button onPress={onDiscard}>Cancel</Button>
            <Button
              variant="primary"
              icon={Check}
              onPress={() => onAttach(withEdits(pending, history.present))}
            >
              Attach this inventory
            </Button>
          </>
        )
      }
    >
      {pending && (
        <>
          <div className="callout">
            <p>
              This is everything that will be stored in the project and sent to agents. It
              includes the <strong>names of your files and folders</strong> and the{" "}
              <strong>column headings</strong> of your tables, which can themselves be sensitive: a
              person&rsquo;s name in a file name, or a heading such as <code>hiv_status</code>.
              Agents may show it to an AI model hosted outside your institution.
            </p>
            <p>
              Untick anything that should not leave your computer. What you leave out is not named
              anywhere; the inventory says only how many files and columns were left out. You can
              also say what a file or column is, and what part a file plays: what you write is
              kept and shown to agents in the same way.{" "}
              <a href={INVENTORY_GUIDE}>What an inventory holds</a>
            </p>
          </div>
          <InventoryEditor
            base={pending.document}
            history={history}
            onHistory={(next) => setChoice({ for: pending, history: next })}
          />
        </>
      )}
    </ModalDialog>
  );
}
