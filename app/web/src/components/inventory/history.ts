/**
 * The inventory editor's undo history. An edit is a value (`@data-director/inventory`'s
 * `InventoryEdits`), so undoing is going back to an earlier value and redoing forward again; an
 * action that changes nothing is not recorded.
 */

import { edit, NO_EDITS, type EditAction, type FileInventory, type InventoryEdits } from "@data-director/inventory";

export interface EditHistory {
  past: readonly InventoryEdits[];
  present: InventoryEdits;
  future: readonly InventoryEdits[];
}

/** A history that starts from `present`: no edits, or what a new scan carried over. */
export function startHistory(present: InventoryEdits = NO_EDITS): EditHistory {
  return { past: [], present, future: [] };
}

/** `history` after `action`, made against `base`. */
export function record(history: EditHistory, base: FileInventory, action: EditAction): EditHistory {
  const next = edit(base, history.present, action);
  if (next === history.present) return history;
  return { past: [...history.past, history.present], present: next, future: [] };
}

export function undo(history: EditHistory): EditHistory {
  const previous = history.past.at(-1);
  if (!previous) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redo(history: EditHistory): EditHistory {
  const [next, ...rest] = history.future;
  if (!next) return history;
  return { past: [...history.past, history.present], present: next, future: rest };
}
