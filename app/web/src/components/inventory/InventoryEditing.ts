/**
 * The inventory view's editing state, shared by its parts (`InventoryView`, `InventoryColumns`):
 * null when the view is read-only.
 */

import type { EditAction, InventoryEdits, InventoryFile } from "@data-director/inventory";
import { createContext } from "react";

/** What the researcher changed, and how to change it, while the view is editing. */
export interface Editing {
  edits: InventoryEdits;
  dispatch: (action: EditAction) => void;
  /** Files that are new since the inventory this one replaces, to be marked so. */
  newPaths?: ReadonlySet<string> | undefined;
}

export interface EditingState extends Editing {
  /** The files as the command found them, by path: the choices a format is chosen from. */
  found: ReadonlyMap<string, InventoryFile>;
}

/** The editing state, or null when the view is read-only. */
export const EditingContext = createContext<EditingState | null>(null);
