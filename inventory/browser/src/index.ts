/**
 * @data-director/inventory: reading a `FileInventory` in TypeScript (README.md). It holds no
 * user interface and no policy: parse a document, summarise it, arrange its files as folders,
 * search them, put its facts into words, and edit it: leave things out and state what the command
 * cannot know (`edit`). It also says in words how to make one, the text the
 * user guide shares (`making`), and which files a person should look at, judged from names alone
 * (`hints`), and where the command found possible personal data (`findings`).
 */

export {
  confidenceLabel,
  findingLabel,
  findingsByPlace,
  PERSONAL_DATA_TEXT,
  personalDataState,
  type PersonalDataState,
} from "./findings";
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
  fileHints,
  HINT_LABELS,
  HINT_LIMITATION,
  HINT_RULES,
  type FileHint,
  type HintKind,
} from "./hints";
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
export {
  asParts,
  NotAPartFolder,
  partFolderProblem,
  partOf,
  partProblems,
  partsOf,
  withPart,
} from "./parts";
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
  type InventoryPart,
  type PersonalDataFinding,
  type TableField,
} from "./types";
export {
  BUNDLE_URL,
  fetchBundle,
  matchesIntegrity,
  serveFrom,
  type BundleAssets,
  type BundleManifest,
} from "./scanner/assets";
export {
  canPickDirectory,
  fromDirectoryHandle,
  fromEntries,
  fromFileList,
  NotAFolder,
  type ChosenFile,
  type ChosenFolder,
  type DirectoryEntryLike,
  type DirectoryHandleLike,
  type EntryLike,
  type FileEntryLike,
  type FileHandleLike,
  type RelativeFile,
} from "./scanner/choose";
export {
  startScan,
  type ScanEvent,
  type ScanHandle,
  type ScanOutcome,
  type ScanRequest,
  type ScanStage,
  type WorkerLike,
} from "./scanner/protocol";
export type { FileProgress } from "./scanner/runtime";
