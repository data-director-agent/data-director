/**
 * The check an inventory goes through before it is attached (#472). Whatever way it came (the
 * Attach button, a drop, a paste or Make an inventory), the researcher sees everything it holds in
 * the inventory editor, may leave out files, folders and columns and say what the command cannot
 * know, and attaches it only by pressing **Attach this inventory**. Until then nothing is attached, so nothing can be sent or recorded. Closing the
 * dialog any other way discards it. The dialog lays out what `@data-director/inventory` says and
 * holds no policy; that only `inventory` content goes to a hosted model by default is the
 * Projects spec's rule, stated here so that the researcher knows it when deciding.
 */

import { Check, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { INVENTORY_GUIDE, withEdits, type AttachedInventory } from "../../conversation/inventory";
import { ReviewDialog } from "../ui/ReviewDialog";
import { startHistory, type EditHistory } from "./history";
import { InventoryEditor } from "./InventoryEditor";

export function InventoryReviewDialog({
  pending,
  onAttach,
  onDiscard,
  attachLabel = "Attach this inventory",
  attachIcon = Check,
  isPending = false,
}: {
  /** The inventory read from the file, not yet attached; null when there is none to check. */
  pending: AttachedInventory | null;
  onAttach: (attached: AttachedInventory) => void;
  onDiscard: () => void;
  /** What the confirming button says, where the inventory is saved rather than attached. */
  attachLabel?: string;
  attachIcon?: LucideIcon;
  isPending?: boolean;
}) {
  // A new inventory starts with nothing changed.
  const [choice, setChoice] = useState<{ for: AttachedInventory | null; history: EditHistory }>(
    () => ({ for: pending, history: startHistory() }),
  );
  if (choice.for !== pending) setChoice({ for: pending, history: startHistory() });
  const history = choice.for === pending ? choice.history : startHistory();
  return (
    <ReviewDialog
      title="Check the inventory"
      isOpen={pending !== null}
      onDiscard={onDiscard}
      attach={{
        label: attachLabel,
        icon: attachIcon,
        isPending,
        onPress: () => pending && onAttach(withEdits(pending, history.present)),
      }}
    >
      {pending && (
        <>
          <div className="callout">
            <p>
              This is stored in the project and sent to agents, including the{" "}
              <strong>names of your files and folders</strong> and the{" "}
              <strong>column headings</strong> of your tables. Agents may show it to an AI model
              hosted outside your institution.
            </p>
            <p>
              Untick anything that should not leave your computer.{" "}
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
    </ReviewDialog>
  );
}
