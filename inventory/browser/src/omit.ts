/**
 * Leaving parts of an inventory out before it is added to a project (#472). A researcher may
 * decide that a file, a folder or a column heading should not leave their computer. What is left
 * out is removed from the document, and one limitation says how much was left out, so that an
 * agent does not take the omission for an absence. The limitation counts what was left out and
 * never names it, since naming it would send the very thing the researcher kept back.
 */

import { assemble } from "./parts";
import type { FileInventory, InventoryFile, InventoryPart } from "./types";

/** What a researcher chose to leave out of an inventory. */
export interface Omission {
  /** Files by path, and folders by path, each of which leaves out every file beneath it. */
  paths: ReadonlySet<string>;
  /** Column headings to leave out, by the path of the table that has them. */
  columns: ReadonlyMap<string, ReadonlySet<string>>;
}

/** Nothing left out. */
export const NOTHING_OMITTED: Omission = { paths: new Set(), columns: new Map() };

/** Whether `path` is one of `paths` or lies in a folder that is. */
export function isOmitted(path: string, paths: ReadonlySet<string>): boolean {
  if (paths.has(path)) return true;
  const parts = path.split("/");
  for (let i = parts.length - 1; i > 0; i -= 1) {
    if (paths.has(parts.slice(0, i).join("/"))) return true;
  }
  return false;
}

/** How many files and columns `omission` leaves out of `inventory`. */
export function countOmitted(
  inventory: FileInventory,
  omission: Omission,
): { files: number; columns: number } {
  let files = 0;
  let columns = 0;
  for (const file of inventory.inventory_files ?? []) {
    if (isOmitted(file.file_path, omission.paths)) {
      files += 1;
      continue;
    }
    const dropped = omission.columns.get(file.file_path);
    if (dropped) columns += (file.file_fields ?? []).filter((f) => dropped.has(f.name)).length;
  }
  return { files, columns };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** "3 files and 1 column", or null when nothing is left out. */
export function describeOmitted(counts: { files: number; columns: number }): string | null {
  const parts = [];
  if (counts.files) parts.push(plural(counts.files, "file", "files"));
  if (counts.columns) parts.push(plural(counts.columns, "column", "columns"));
  return parts.length ? parts.join(" and ") : null;
}

/**
 * `inventory` without what `omission` leaves out. A limitation already in the inventory that
 * names a file or folder left out (`dd-inventory`'s "… could not be read") is removed with it,
 * and one limitation is added that says how much was left out without naming any of it. With
 * nothing left out, `inventory` is returned as it is.
 */
export function omit(inventory: FileInventory, omission: Omission): FileInventory {
  if (inventory.inventory_parts?.length) return omitFromParts(inventory, omission);
  const counts = countOmitted(inventory, omission);
  const described = describeOmitted(counts);
  if (!described) return inventory;

  const named: string[] = [];
  const kept: InventoryFile[] = [];
  for (const file of inventory.inventory_files ?? []) {
    if (isOmitted(file.file_path, omission.paths)) {
      named.push(file.file_path);
      continue;
    }
    const dropped = omission.columns.get(file.file_path);
    if (!dropped || !file.file_fields?.some((f) => dropped.has(f.name))) {
      kept.push(file);
      continue;
    }
    kept.push({ ...file, file_fields: file.file_fields.filter((f) => !dropped.has(f.name)) });
  }
  for (const path of omission.paths) named.push(`${path}/`);

  const limitations = (inventory.inventory_limitations ?? []).filter(
    (sentence) => !named.some((name) => name && sentence.includes(name)),
  );
  limitations.push(leftOutSentence(described));
  return { ...inventory, inventory_files: kept, inventory_limitations: limitations };
}

function leftOutSentence(described: string): string {
  return (
    `Before this inventory was added, the researcher left out ${described}. That they are not ` +
    "listed here does not mean they are not in the dataset."
  );
}

function within(path: string, folder: string): boolean {
  return path === folder || path.startsWith(`${folder}/`);
}

/**
 * `omit` for an inventory made of parts. Each part's own limitations are cleaned of what names a
 * file left out, and gain a sentence counting what was left out of that part, so the count stays
 * with the part when another folder is updated. A part whose folder is left out is dropped, and
 * what it held is counted among the limitations that concern no one part.
 */
function omitFromParts(inventory: FileInventory, omission: Omission): FileInventory {
  if (!describeOmitted(countOmitted(inventory, omission))) return inventory;
  const parts = inventory.inventory_parts ?? [];
  const leads = parts.map((p) => `In ${p.part_folder}: `);
  const general = (inventory.inventory_limitations ?? []).filter(
    (sentence) => !leads.some((l) => sentence.startsWith(l)),
  );
  const kept: InventoryPart[] = [];
  let dropped = { files: 0, columns: 0 };
  for (const part of parts) {
    const folder = part.part_folder;
    const own: FileInventory = {
      ...inventory,
      inventory_files: (inventory.inventory_files ?? []).filter((f) => within(f.file_path, folder)),
    };
    const counts = countOmitted(own, omission);
    if (isOmitted(folder, omission.paths)) {
      dropped = { files: dropped.files + counts.files, columns: dropped.columns + counts.columns };
      continue;
    }
    const described = describeOmitted(counts);
    if (!described) {
      kept.push(part);
      continue;
    }
    const named = [...(own.inventory_files ?? []).map((f) => f.file_path), ...omission.paths]
      .filter((path) => within(path, folder) && path !== folder && isOmitted(path, omission.paths))
      .map((path) => path.slice(folder.length + 1));
    const limitations = (part.part_limitations ?? []).filter(
      (sentence) => !named.some((name) => name && sentence.includes(name)),
    );
    limitations.push(leftOutSentence(described));
    kept.push({ ...part, part_limitations: limitations });
  }
  const droppedDescribed = describeOmitted(dropped);
  if (droppedDescribed) general.push(leftOutSentence(droppedDescribed));
  const files = (inventory.inventory_files ?? [])
    .filter((f) => !isOmitted(f.file_path, omission.paths))
    .map((f) => {
      const columns = omission.columns.get(f.file_path);
      if (!columns || !f.file_fields?.some((c) => columns.has(c.name))) return f;
      return { ...f, file_fields: f.file_fields.filter((c) => !columns.has(c.name)) };
    });
  return assemble(inventory, files, kept, general);
}
