/**
 * What the transcript shows between sending a message and the reply arriving: the message
 * itself, so it is not lost from view, and a line saying the orchestrator is working, by its name,
 * with three dots that pulse. It is laid out as a turn is, so nothing moves when the reply comes. The dots are decoration (`aria-hidden`); the words carry the state, and the
 * page's live region announces it. With reduced motion the dots stay still.
 */

import "./Pending.css";

import type { AttachedDocument } from "../../conversation/documentation";
import type { AttachedInventory } from "../../conversation/inventory";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";
import { Speaker } from "./Speaker";

export function Pending({
  agentId,
  agentName = agentId,
  message,
  inventory = null,
  document = null,
}: {
  agentId: string;
  /** What to call the agent: its card's title, or its id, which it is when not given. */
  agentName?: string;
  message: string;
  inventory?: AttachedInventory | null;
  document?: AttachedDocument | null;
}) {
  return (
    <li className="turn pending">
      <div className="turn-person">
        <Speaker />
        <p>{message}</p>
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
      </div>
      <div className="turn-agent">
        <p className="muted">
          {agentName === agentId ? <code>{agentId}</code> : agentName} is working on a reply
          <span className="pending-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </p>
      </div>
    </li>
  );
}
