/**
 * @data-director/inventory: reading a `FileInventory` in TypeScript (README.md). It holds no
 * user interface and no policy: parse a document, summarise it, arrange its files as folders,
 * search them, put its facts into words, and edit it: leave things out and state what the command
 * cannot know (`edit`). It also says in words how to make one, the text the
 * user guide shares (`making`).
 */

export {
  describeInventory,
  formatBytes,
  formatDate,
  formatFileCount,
  identificationLabel,
  pronomUrl,
} from "./format";
export {
  applyEdits,
  canChooseFormat,
  carryOver,
  countEdits,
  DESCRIPTION_LIMIT,
  describeEdits,
  diffInventories,
  edit,
  isValidFormat,
  NO_EDITS,
  type EditAction,
  type EditCounts,
  type FileStatement,
  type FormatStatement,
  type InventoryDiff,
  type InventoryEdits,
} from "./edit";
export {
  MAKING_AN_INVENTORY,
  systemFromPlatform,
  type MakingAnInventory,
  type SystemId,
  type SystemInstructions,
} from "./making";
export {
  countOmitted,
  describeOmitted,
  isOmitted,
  NOTHING_OMITTED,
  omit,
  type Omission,
} from "./omit";
export { asInventory, looksLikeInventory, NotAnInventory, parseInventory } from "./parse";
export { searchFiles } from "./search";
export { files, summarise, type FormatGroup, type InventorySummary, type TableSummary } from "./summary";
export { folderTree, type FileNode, type FolderNode, type TreeNode } from "./tree";
export {
  FILE_ROLES,
  IDENTIFICATION_METHODS,
  type FileInventory,
  type FileRole,
  type IdentificationMethod,
  type InventoryFile,
  type TableField,
} from "./types";
