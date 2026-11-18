/**
 * The `FileInventory` class of the core contract, as TypeScript types. Slot names are the
 * contract's (`sdk/src/dd_sdk/schema/data_director.yaml`), so a document `dd-inventory` writes
 * is one of these as it stands.
 */

/**
 * How a file's format was identified: by the command, from strongest to weakest, or chosen by the
 * researcher where the command found several matches or none.
 */
export type IdentificationMethod = "signature" | "container" | "extension" | "none" | "researcher";

/** The methods in the order they are listed: the command's from strongest, then the researcher's. */
export const IDENTIFICATION_METHODS: readonly IdentificationMethod[] = [
  "signature",
  "container",
  "extension",
  "none",
  "researcher",
];

/** What part a file plays in a dataset, as the researcher states it. */
export type FileRole = "data" | "documentation" | "code" | "other";

/** The roles in the order a person is offered them. */
export const FILE_ROLES: readonly FileRole[] = ["data", "documentation", "code", "other"];

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
  /** What the file is, in the researcher's words; the command never fills it. */
  file_description?: string;
  /** What part the file plays, as the researcher states it; unset means not stated. */
  file_role?: FileRole;
}

/** What a personal-data finding took the data to be: from values first, then from names. */
export type PersonalDataKind =
  | "email address"
  | "phone number"
  | "NHS number"
  | "National Insurance number"
  | "postcode"
  | "passport number"
  | "driving licence number"
  | "bank account number"
  | "payment card number"
  | "IP address"
  | "person name"
  | "direct identifier"
  | "indirect identifier"
  | "special category"
  | "location";

/** What part of a file a finding concerns. */
export type FindingTarget = "column" | "field name" | "file name" | "text";

/**
 * Where the inventory command found what may be personal data (docs/specs/personal-data.md).
 * It never holds a value: a kind, a place, bands and the detector.
 */
export interface PersonalDataFinding {
  finding_kind: PersonalDataKind;
  /** A file's path, as `file_path`; or a folder's, ending in `/`, for its name. */
  finding_file: string;
  finding_target: FindingTarget;
  /** The column, for a column or a field name. */
  finding_column?: string;
  finding_proportion?: "under 1%" | "1 to 10%" | "10 to 50%" | "over 50%";
  finding_confidence: "low" | "medium" | "high";
  finding_detector: string;
  /** The sampled values of a column, or the characters of a text file. */
  finding_examined?: number;
}

/**
 * One scan of one folder, mounted at a folder name, in an inventory made of several. Every file
 * of the inventory lies under exactly one part's folder.
 */
export interface InventoryPart {
  /** Relative, with forward slashes, such as `instrument` or `raw/2024`. */
  part_folder: string;
  part_tool: string;
  part_tool_version: string;
  part_identified_with?: string;
  /** ISO 8601. */
  part_made_at: string;
  /** As the scan wrote them: paths in them are relative to the part's folder. */
  part_limitations?: string[];
  /** The part's findings, with paths that begin with its folder; absent, no detector ran. */
  part_personal_data?: PersonalDataFinding[];
}

/**
 * The facts about a dataset's files that a project holds in place of the files. Without
 * `inventory_parts` it is one scan of one folder; with them, the top-level tool, version and date
 * are the latest part's, and `inventory_limitations` holds each part's, after `In <folder>: `.
 */
export interface FileInventory {
  schema_class: "FileInventory";
  inventory_files?: InventoryFile[];
  inventory_tool: string;
  inventory_tool_version: string;
  inventory_identified_with?: string;
  /** ISO 8601. */
  inventory_made_at: string;
  inventory_limitations?: string[];
  inventory_parts?: InventoryPart[];
  /**
   * Where possible personal data were found. Absent, no detector ran; empty, one ran and found
   * nothing, which does not mean there is none. With parts, all of theirs.
   */
  inventory_personal_data?: PersonalDataFinding[];
}
