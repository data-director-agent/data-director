/** Finding files in an inventory too large to read through. */

import type { InventoryFile } from "./types";

/**
 * The files whose path, media type, PRONOM identifier or a column name contains `query`, ignoring
 * case. An empty query matches every file.
 */
export function searchFiles(files: readonly InventoryFile[], query: string): InventoryFile[] {
  const needle = query.trim().toLocaleLowerCase("en-GB");
  if (!needle) return [...files];
  const has = (text: string | undefined) => text?.toLocaleLowerCase("en-GB").includes(needle) ?? false;
  return files.filter(
    (file) =>
      has(file.file_path) ||
      has(file.file_media_type) ||
      (file.file_pronom_ids ?? []).some(has) ||
      (file.file_fields ?? []).some((field) => has(field.name)),
  );
}
