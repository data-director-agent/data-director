/**
 * What the transcript shows between sending a message and the reply arriving: the message
 * itself, so it is not lost from view, and a line saying the orchestrator is working, with three
 * dots that pulse. The dots are decoration (`aria-hidden`); the words carry the state, and the
 * page's live region announces it. With reduced motion the dots stay still.
 */

import "./Pending.css";

import type { AttachedDocument } from "../../conversation/documentation";
import type { AttachedInventory } from "../../conversation/inventory";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";

export function Pending({
  agentId,
  message,
  inventory = null,
  document = null,
}: {
  agentId: string;
  message: string;
  inventory?: AttachedInventory | null;
  document?: AttachedDocument | null;
}) {
  return (
    <li className="pending">
      <p>
        <strong>You:</strong> {message}
      </p>
      {inventory && (
        <p>
          <InventoryChip
            fileCount={inventory.fileCount}
            madeAt={inventory.madeAt}
            name={inventory.name}
            source={{ document: inventory.document }}
          />
        </p>
      )}
      {document && (
        <p>
          <DocumentChip name={document.name} size={document.size} />
        </p>
      )}
      <p className="muted">
        <code>{agentId}</code> is working on a reply
        <span className="pending-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </p>
    </li>
  );
}
