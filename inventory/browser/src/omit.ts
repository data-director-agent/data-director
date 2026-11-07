/**
 * Leaving parts of an inventory out before it is added to a project (#472). A researcher may
 * decide that a file, a folder or a column heading should not leave their computer. What is left
 * out is removed from the document, and one limitation says how much was left out, so that an
 * agent does not take the omission for an absence. The limitation counts what was left out and
 * never names it, since naming it would send the very thing the researcher kept back.
 */

import type { FileInventory, InventoryFile } from "./types";

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
  limitations.push(
    `Before this inventory was added, the researcher left out ${described}. That they are not ` +
      "listed here does not mean they are not in the dataset.",
  );
  return { ...inventory, inventory_files: kept, inventory_limitations: limitations };
}
