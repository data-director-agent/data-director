/**
 * @data-director/inventory: reading a `FileInventory` in TypeScript (README.md). It holds no
 * user interface and no policy: parse a document, summarise it, arrange its files as folders,
 * search them, and put its facts into words.
 */

export {
  describeInventory,
  formatBytes,
  formatDate,
  formatFileCount,
  identificationLabel,
  pronomUrl,
} from "./format";
export { asInventory, looksLikeInventory, NotAnInventory, parseInventory } from "./parse";
export { searchFiles } from "./search";
export { files, summarise, type FormatGroup, type InventorySummary, type TableSummary } from "./summary";
export { folderTree, type FileNode, type FolderNode, type TreeNode } from "./tree";
export {
  IDENTIFICATION_METHODS,
  type FileInventory,
  type IdentificationMethod,
  type InventoryFile,
  type TableField,
} from "./types";
