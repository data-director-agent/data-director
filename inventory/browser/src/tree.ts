/** An inventory's files as the folders they sit in. */

import type { InventoryFile } from "./types";

export interface FolderNode {
  kind: "folder";
  /** The folder's own name; the root's is "". */
  name: string;
  /** From the dataset's root, with forward slashes; the root's is "". */
  path: string;
  /** Folders first, then files, each sorted by name. */
  children: TreeNode[];
  /** Every file below the folder, at any depth. */
  fileCount: number;
  bytes: number;
}

export interface FileNode {
  kind: "file";
  name: string;
  path: string;
  file: InventoryFile;
}

export type TreeNode = FolderNode | FileNode;

const byName = new Intl.Collator("en-GB", { numeric: true }).compare;

/** The folder tree of `files`, under a root folder named "". */
export function folderTree(files: readonly InventoryFile[]): FolderNode {
  const root: FolderNode = { kind: "folder", name: "", path: "", children: [], fileCount: 0, bytes: 0 };
  for (const file of files) {
    const parts = file.file_path.split("/").filter(Boolean);
    const name = parts.pop() ?? file.file_path;
    let folder = root;
    const trail = [root];
    for (const part of parts) {
      let next = folder.children.find(
        (child): child is FolderNode => child.kind === "folder" && child.name === part,
      );
      if (!next) {
        const path = folder.path ? `${folder.path}/${part}` : part;
        next = { kind: "folder", name: part, path, children: [], fileCount: 0, bytes: 0 };
        folder.children.push(next);
      }
      folder = next;
      trail.push(folder);
    }
    folder.children.push({ kind: "file", name, path: file.file_path, file });
    for (const ancestor of trail) {
      ancestor.fileCount += 1;
      ancestor.bytes += file.file_size;
    }
  }
  sort(root);
  return root;
}

function sort(folder: FolderNode): void {
  folder.children.sort((a, b) =>
    a.kind === b.kind ? byName(a.name, b.name) : a.kind === "folder" ? -1 : 1,
  );
  for (const child of folder.children) if (child.kind === "folder") sort(child);
}
