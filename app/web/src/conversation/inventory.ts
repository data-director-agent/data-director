/**
 * A `dd-inventory` file the researcher attaches to a message (docs/specs/app.md). The file is
 * read here only to tell whether it looks like an inventory and to name it on a chip; the server
 * checks it against the `FileInventory` class schema, and the conversation's project keeps it
 * (docs/specs/projects.md). Its text never goes into the message.
 */

/** The user guide's page on making an inventory, linked beside the attach button. */
export const INVENTORY_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/making-an-inventory/";

/** An inventory read from a file, with what its chip shows. */
export interface AttachedInventory {
  /** The document, sent as the turn's `inventory`. */
  document: Record<string, unknown>;
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

/** A file that is not an inventory, with a sentence saying why. */
export class NotAnInventory extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `text` read as an inventory, or `NotAnInventory` saying why it is not one. */
export function readInventory(text: string, name: string | null): AttachedInventory {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new NotAnInventory("This file is not JSON, so it is not an inventory.");
  }
  if (!isRecord(parsed) || parsed.schema_class !== "FileInventory") {
    throw new NotAnInventory(
      "This file is not an inventory: it does not say it is a FileInventory, as the file " +
        "dd-inventory writes does.",
    );
  }
  const files = parsed.inventory_files;
  const madeAt = parsed.inventory_made_at;
  if ((files !== undefined && !Array.isArray(files)) || typeof madeAt !== "string") {
    throw new NotAnInventory("This inventory is incomplete: it lists no files or no date.");
  }
  return { document: parsed, name, fileCount: files?.length ?? 0, madeAt };
}

/** Whether pasted text is a whole inventory, which then becomes a chip instead of text. */
export function looksLikeInventory(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.startsWith("{") && trimmed.includes('"FileInventory"');
}

const DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "42 files, made 1 Nov 2026". */
export function describeInventory(fileCount: number, madeAt: string): string {
  const files = fileCount === 1 ? "1 file" : `${fileCount} files`;
  const made = new Date(madeAt);
  return Number.isNaN(made.getTime()) ? files : `${files}, made ${DATE.format(made)}`;
}
