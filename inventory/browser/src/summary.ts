/** What an inventory amounts to: totals, formats, how well they were identified, and tables. */

import {
  IDENTIFICATION_METHODS,
  type FileInventory,
  type IdentificationMethod,
  type InventoryFile,
  type TableField,
} from "./types";

/** The files of one media type. */
export interface FormatGroup {
  /** The media type, or null for the files that have none. */
  mediaType: string | null;
  /** Every PRONOM identifier the group's files matched, sorted. */
  pronomIds: string[];
  fileCount: number;
  bytes: number;
}

/** A file that is a table, with its fields. */
export interface TableSummary {
  path: string;
  fields: TableField[];
}

export interface InventorySummary {
  fileCount: number;
  bytes: number;
  /** Largest share of bytes first. */
  formats: FormatGroup[];
  /** How many files each method identified, strongest first; every method is present. */
  identification: Record<IdentificationMethod, number>;
  /** Files that matched more than one PRONOM identifier. */
  ambiguous: InventoryFile[];
  /** Files whose format nothing recognised. */
  unknown: InventoryFile[];
  tables: TableSummary[];
  limitations: string[];
}

export function files(inventory: FileInventory): InventoryFile[] {
  return inventory.inventory_files ?? [];
}

/** The summary of `inventory`. */
export function summarise(inventory: FileInventory): InventorySummary {
  const all = files(inventory);
  const identification = Object.fromEntries(IDENTIFICATION_METHODS.map((m) => [m, 0])) as Record<
    IdentificationMethod,
    number
  >;
  const formats = new Map<string | null, FormatGroup & { ids: Set<string> }>();
  for (const file of all) {
    identification[file.file_identified_by] += 1;
    const key = file.file_media_type ?? null;
    let group = formats.get(key);
    if (!group) {
      group = { mediaType: key, pronomIds: [], fileCount: 0, bytes: 0, ids: new Set() };
      formats.set(key, group);
    }
    group.fileCount += 1;
    group.bytes += file.file_size;
    for (const id of file.file_pronom_ids ?? []) group.ids.add(id);
  }
  return {
    fileCount: all.length,
    bytes: all.reduce((sum, file) => sum + file.file_size, 0),
    formats: [...formats.values()]
      .map(({ ids, ...group }) => ({ ...group, pronomIds: [...ids].sort() }))
      .sort((a, b) => b.bytes - a.bytes || b.fileCount - a.fileCount),
    identification,
    ambiguous: all.filter((file) => (file.file_pronom_ids?.length ?? 0) > 1),
    unknown: all.filter((file) => file.file_identified_by === "none"),
    tables: all
      .filter((file) => file.file_fields?.length)
      .map((file) => ({ path: file.file_path, fields: file.file_fields ?? [] })),
    limitations: inventory.inventory_limitations ?? [],
  };
}
