/**
 * The check an inventory goes through before it is attached (#472). Whatever way it came (the
 * Attach button, a drop, a paste or Make an inventory), the researcher sees everything it holds,
 * may leave out files, folders and columns, and attaches it only by pressing **Attach this
 * inventory**. Until then nothing is attached, so nothing can be sent or recorded. Closing the
 * dialog any other way discards it. The dialog lays out what `@data-director/inventory` says and
 * holds no policy; that only `inventory` content goes to a hosted model by default is the
 * Projects spec's rule, stated here so that the researcher knows it when deciding.
 */

import { NOTHING_OMITTED, type Omission } from "@data-director/inventory";
import { Check } from "lucide-react";
import { useState } from "react";

import { INVENTORY_GUIDE, withOmission, type AttachedInventory } from "../../conversation/inventory";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { InventoryView } from "./InventoryView";

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
  // A new inventory starts with nothing left out.
  const [choice, setChoice] = useState<{ for: AttachedInventory | null; omission: Omission }>({
    for: pending,
    omission: NOTHING_OMITTED,
  });
  if (choice.for !== pending) setChoice({ for: pending, omission: NOTHING_OMITTED });
  const omission = choice.for === pending ? choice.omission : NOTHING_OMITTED;
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
              onPress={() => onAttach(withOmission(pending, omission))}
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
              anywhere; the inventory says only how many files and columns were left out.{" "}
              <a href={INVENTORY_GUIDE}>What an inventory holds</a>
            </p>
          </div>
          <InventoryView
            inventory={pending.document}
            omission={omission}
            onOmit={(next) => setChoice({ for: pending, omission: next })}
          />
        </>
      )}
    </ModalDialog>
  );
}
