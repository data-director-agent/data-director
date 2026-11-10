/**
 * A supporting document shown as a chip, never as its text: in the message box while it is
 * attached, and in the transcript on the turn it was given. The chip names the file and its
 * size; in the message box a button removes it.
 */

import "./InventoryChip.css";

import { FileText, X } from "lucide-react";
import { describeSize } from "../../conversation/documentation";
import { Button } from "../ui/Button";

export function DocumentChip({
  name,
  size,
  onRemove,
}: {
  name: string;
  size: number;
  onRemove?: () => void;
}) {
  return (
    <span className="inventory-chip">
      <FileText className="inventory-chip-icon" size="1.125em" aria-hidden="true" />
      <span>
        Document: {name} <span className="muted">({describeSize(size)})</span>
      </span>
      {onRemove && (
        <Button size="small" variant="quiet" icon={X} onPress={onRemove} aria-label={`Remove ${name}`} />
      )}
    </span>
  );
}
