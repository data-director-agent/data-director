/**
 * A `dd-inventory` file the researcher attaches to a message (docs/specs/app.md). The file is
 * read here to tell whether it is an inventory, to name it on a chip and to show it in the
 * inventory dialog; reading it is `@data-director/inventory`'s, which holds no policy. The server
 * checks it against the `FileInventory` class schema, and the conversation's project keeps it
 * (docs/specs/projects.md). Its text never goes into the message.
 */

import {
  applyEdits,
  asInventory,
  parseInventory,
  type FileInventory,
  type InventoryEdits,
} from "@data-director/inventory";

export { describeInventory, looksLikeInventory, NotAnInventory } from "@data-director/inventory";

/** The user guide's page on making an inventory, linked beside the attach button. */
export const INVENTORY_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/making-an-inventory/";

/** An inventory read from a file, with what its chip shows. */
export interface AttachedInventory {
  /** The document, sent as the turn's `inventory`. */
  document: FileInventory;
  /** The file's name, or null when it was pasted. */
  name: string | null;
  fileCount: number;
  madeAt: string;
}

/** What the server says the conversation's project holds (`GET /api/conversations/{id}`). */
export interface ProjectInventory {
  digest: string;
  file_count: number;
  inventory_made_at: string;
  added_at: string;
}

/** What the conductor told a turn's agent of the project's inventory (`Message.project_inventory`). */
export interface InventorySummary {
  inventory_digest: string;
  inventory_file_count: number;
  inventory_tool: string;
  inventory_tool_version: string;
  inventory_made_at: string;
  inventory_limitations?: string[];
}

/**
 * Where the inventory dialog gets the whole inventory: one in hand (attached, not yet sent), or
 * one to fetch (the project's, `GET /api/projects/{id}/inventory`). A fetched one is read with
 * `asInventory` before it is shown.
 */
export type InventorySource =
  | { document: FileInventory }
  | { load: (signal: AbortSignal) => Promise<unknown> };

function attachedFrom(document: FileInventory, name: string | null): AttachedInventory {
  return {
    document,
    name,
    fileCount: document.inventory_files?.length ?? 0,
    madeAt: document.inventory_made_at,
  };
}

/** `text` read as an inventory, or `NotAnInventory` saying why it is not one. */
export function readInventory(text: string, name: string | null): AttachedInventory {
  return attachedFrom(parseInventory(text), name);
}

/**
 * `attached` as the researcher edited it when checking it (#472): without what they left out,
 * with one limitation counting it, and with what they stated beside the facts. This is the
 * document that is sent, and so all the project keeps.
 */
export function withEdits(attached: AttachedInventory, edits: InventoryEdits): AttachedInventory {
  return attachedFrom(applyEdits(attached.document, edits), attached.name);
}

/** The inventory a source gives, read as one. */
export async function inventoryFrom(source: InventorySource, signal: AbortSignal): Promise<FileInventory> {
  return "document" in source ? source.document : asInventory(await source.load(signal));
}
