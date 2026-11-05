/**
 * An inventory shown as a chip, never as its JSON (#443): in the message box while it is
 * attached, in the transcript on the turn it was given, and beside the conversation as what the
 * project holds. The chip's text names it; in the message box a button removes it.
 */

import "./InventoryChip.css";

import { FileSpreadsheet, X } from "lucide-react";
import { describeInventory } from "../../conversation/inventory";
import { Button } from "../ui/Button";

export function InventoryChip({
  fileCount,
  madeAt,
  name = null,
  onRemove,
}: {
  fileCount: number;
  madeAt: string;
  name?: string | null;
  onRemove?: () => void;
}) {
  return (
    <span className="inventory-chip">
      <FileSpreadsheet className="inventory-chip-icon" size="1.125em" aria-hidden="true" />
      <span>
        Inventory: {describeInventory(fileCount, madeAt)}
        {name && <span className="muted"> ({name})</span>}
      </span>
      {onRemove && (
        <Button size="small" variant="quiet" icon={X} onPress={onRemove} aria-label="Remove inventory" />
      )}
    </span>
  );
}
