/**
 * An inventory shown as a chip, never as its JSON (#443): in the message box while it is
 * attached, in the transcript on the turn it was given, and beside the conversation as what the
 * project holds. The chip's text names it; given a `source`, a button opens it in readable form
 * (#472), and in the message box a button removes it.
 */

import "./InventoryChip.css";

import { FileSpreadsheet, X } from "lucide-react";
import { describeInventory, type InventorySource } from "../../conversation/inventory";
import { InventoryDialog } from "../inventory/InventoryDialog";
import { Button } from "../ui/Button";

export function InventoryChip({
  fileCount,
  madeAt,
  name = null,
  source,
  onRemove,
}: {
  fileCount: number;
  madeAt: string;
  name?: string | null;
  source?: InventorySource | undefined;
  onRemove?: () => void;
}) {
  return (
    <span className="inventory-chip">
      <FileSpreadsheet className="inventory-chip-icon" size="1.125em" aria-hidden="true" />
      <span>
        Inventory: {describeInventory(fileCount, madeAt)}
        {name && <span className="muted"> ({name})</span>}
      </span>
      {source && <InventoryDialog source={source} />}
      {onRemove && (
        <Button size="small" variant="quiet" icon={X} onPress={onRemove} aria-label="Remove inventory" />
      )}
    </span>
  );
}
