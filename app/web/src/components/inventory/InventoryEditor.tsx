/**
 * The inventory editor: one surface for leaving things out of an inventory, saying what the
 * command cannot know, and seeing what a new scan changed (docs/specs/projects.md). It is used
 * when an inventory is checked before it is attached and when a project's inventory is revised.
 *
 * The editor holds no document of its own. Its caller keeps an `EditHistory` and the inventory
 * it started from, and writes the edits in with `applyEdits` only when the researcher confirms,
 * so closing without confirming changes nothing.
 */

import type { FileInventory, InventoryDiff } from "@data-director/inventory";
import { Redo2, Undo2 } from "lucide-react";
import { useMemo } from "react";

import { Button } from "../ui/Button";
import { record, redo, undo, type EditHistory } from "./history";
import { InventoryView } from "./InventoryView";

/** What a new scan changed beside the inventory the project held. */
export interface Rescan {
  diff: InventoryDiff;
  /** Files the researcher had said something about that the new scan no longer lists. */
  orphaned: readonly string[];
}

export function InventoryEditor({
  base,
  history,
  onHistory,
  rescan,
}: {
  base: FileInventory;
  history: EditHistory;
  onHistory: (history: EditHistory) => void;
  rescan?: Rescan | undefined;
}) {
  const newPaths = useMemo(() => (rescan ? new Set(rescan.diff.added) : undefined), [rescan]);
  const editing = useMemo(
    () => ({
      edits: history.present,
      dispatch: (action: Parameters<typeof record>[2]) => onHistory(record(history, base, action)),
      newPaths,
    }),
    [history, base, onHistory, newPaths],
  );
  return (
    <div className="inventory-editor">
      {rescan && <WhatChanged rescan={rescan} />}
      <div className="inventory-editor-tools" role="toolbar" aria-label="Changes">
        <Button
          size="small"
          icon={Undo2}
          isDisabled={history.past.length === 0}
          onPress={() => onHistory(undo(history))}
        >
          Undo
        </Button>
        <Button
          size="small"
          icon={Redo2}
          isDisabled={history.future.length === 0}
          onPress={() => onHistory(redo(history))}
        >
          Redo
        </Button>
      </div>
      <InventoryView inventory={base} editing={editing} />
    </div>
  );
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The new scan beside the inventory it replaces, and what could not be carried over. */
function WhatChanged({ rescan }: { rescan: Rescan }) {
  const { diff, orphaned } = rescan;
  return (
    <section aria-labelledby="inventory-what-changed" className="callout">
      <h3 id="inventory-what-changed">What the new scan changed</h3>
      <ul className="plain-list">
        <li>{count(diff.added.length, "file is new", "files are new")}</li>
        <li>{count(diff.changed.length, "file has changed", "files have changed")}</li>
        <li>{count(diff.removed.length, "file is gone", "files are gone")}</li>
        <li>{count(diff.unchanged, "file is unchanged", "files are unchanged")}</li>
      </ul>
      <p>
        What you said about files before is kept where the file is still there. A format you chose
        is kept only for a file that has not changed.
      </p>
      {diff.added.length > 0 && (
        <p>
          <strong>Check the new files.</strong> Anything you left out of the earlier inventory was
          never kept, so it is listed again here and you need to leave it out again.
        </p>
      )}
      {orphaned.length > 0 && (
        <details>
          <summary>
            {count(orphaned.length, "file you described is", "files you described are")} no longer
            listed
          </summary>
          <ul>
            {orphaned.map((path) => (
              <li key={path} className="inventory-file-name">
                {path}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
