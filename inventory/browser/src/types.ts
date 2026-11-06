/**
 * The `FileInventory` class of the core contract, as TypeScript types. Slot names are the
 * contract's (`sdk/src/dd_sdk/schema/data_director.yaml`), so a document `dd-inventory` writes
 * is one of these as it stands.
 */

/** How a file's format was identified, from strongest to weakest. */
export type IdentificationMethod = "signature" | "container" | "extension" | "none";

/** The methods in order of strength, strongest first. */
export const IDENTIFICATION_METHODS: readonly IdentificationMethod[] = [
  "signature",
  "container",
  "extension",
  "none",
];

/** One field of a table, mirroring a Frictionless Table Schema field descriptor. */
export interface TableField {
  name: string;
  field_type?: string;
  field_format?: string;
  field_description?: string;
}

/** One file of a dataset, as the inventory command found it. */
export interface InventoryFile {
  /** Relative to the dataset's root folder, with forward slashes. */
  file_path: string;
  /** In bytes. */
  file_size: number;
  file_sha256: string;
  file_media_type?: string;
  /** Every PRONOM identifier the file matched: more than one is ambiguous, none is unknown. */
  file_pronom_ids?: string[];
  file_identified_by: IdentificationMethod;
  /** For a table, its fields inferred from a sample of rows. */
  file_fields?: TableField[];
}

/** The facts about a dataset's files that a project holds in place of the files. */
export interface FileInventory {
  schema_class: "FileInventory";
  inventory_files?: InventoryFile[];
  inventory_tool: string;
  inventory_tool_version: string;
  inventory_identified_with?: string;
  /** ISO 8601. */
  inventory_made_at: string;
  inventory_limitations?: string[];
}
