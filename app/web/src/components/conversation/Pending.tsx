/**
 * What the transcript shows between sending a message and the reply arriving: the message
 * itself, so it is not lost from view, and a line saying the orchestrator is working, by its name,
 * with three dots that pulse. It is laid out as a turn is, so nothing moves when the reply comes. The dots are decoration (`aria-hidden`); the words carry the state, and the
 * page's live region announces it. With reduced motion the dots stay still.
 *
 * Below it, the turn's run is drawn live from its stream, with Cancel (`LiveRun`). A run that
 * ended without finishing stays here with its own screen; once the server has stored the turn,
 * the transcript shows the message, so it is not shown twice.
 */

import "./Pending.css";

import type { AttachedDocument } from "../../conversation/documentation";
import type { AttachedInventory } from "../../conversation/inventory";
import { hasEnded } from "../../run/reduce";
import { LiveRun } from "../run/LiveRun";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";
import { Speaker } from "./Speaker";
import type { LiveRun as Live } from "./useConversationTurns";

export function Pending({
  agentId,
  agentName = agentId,
  message,
  inventory = null,
  document = null,
  live = null,
}: {
  agentId: string;
  /** What to call the agent: its card's title, or its id, which it is when not given. */
  agentName?: string;
  message: string;
  inventory?: AttachedInventory | null;
  document?: AttachedDocument | null;
  /** The turn's run, as its stream has drawn it so far. */
  live?: Live | null;
}) {
  const working = !live || !hasEnded(live.state);
  return (
    <li className="turn pending">
      {!live?.stored && (
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
      )}
      <div className="turn-agent">
        {working && (
          <p className="muted">
            {agentName === agentId ? <code>{agentId}</code> : agentName} is
            working on a reply
            <span className="pending-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </p>
        )}
        {live && (
          <LiveRun
            run={live.state}
            cancelling={live.cancelling}
            onCancel={live.cancel}
            idPrefix="live-run"
          />
        )}
      </div>
    </li>
  );
}
