/**
 * The folder a researcher chooses, by any of the browser's three routes, as files with paths
 * relative to it. Each route yields the same `ChosenFolder`, which the scanner mounts read-only
 * (`worker.ts`). Hidden files are kept: the command skips and counts them itself, as it does on
 * disk.
 *
 * The functions take minimal structural types rather than the DOM's, so that they can be tested
 * without a browser.
 */

/** A file of the chosen folder, at its path relative to the folder, with `/` between names. */
export interface ChosenFile {
  path: string;
  file: Blob;
}

/** A chosen folder: its own name, and every file under it, sorted by path. */
export interface ChosenFolder {
  name: string;
  files: ChosenFile[];
}

/** A `FileSystemDirectoryHandle` from `showDirectoryPicker`, as far as it is used here. */
export interface DirectoryHandleLike {
  kind: "directory";
  name: string;
  values(): AsyncIterable<DirectoryHandleLike | FileHandleLike>;
}

/** A `FileSystemFileHandle`, as far as it is used here. */
export interface FileHandleLike {
  kind: "file";
  name: string;
  getFile(): Promise<Blob>;
}

/** A file from `<input type="file" webkitdirectory>`, which names it from the chosen folder. */
export interface RelativeFile extends Blob {
  webkitRelativePath: string;
}

/** A `FileSystemEntry` from a dropped item's `webkitGetAsEntry()`, as far as it is used here. */
export type EntryLike = FileEntryLike | DirectoryEntryLike;

export interface FileEntryLike {
  isFile: true;
  isDirectory: false;
  name: string;
  file(success: (file: Blob) => void, failure: (error: unknown) => void): void;
}

export interface DirectoryEntryLike {
  isFile: false;
  isDirectory: true;
  name: string;
  createReader(): {
    readEntries(success: (entries: EntryLike[]) => void, failure: (error: unknown) => void): void;
  };
}

/** Why a choice cannot be scanned. A sentence for the researcher. */
export class NotAFolder extends Error {
  override name = "NotAFolder";
}

function sorted(name: string, files: ChosenFile[]): ChosenFolder {
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return { name, files };
}

/** Whether this browser offers `showDirectoryPicker`, the route that asks to read, not upload. */
export function canPickDirectory(scope: object = globalThis): boolean {
  return typeof (scope as { showDirectoryPicker?: unknown }).showDirectoryPicker === "function";
}

/** The files under a folder chosen with `showDirectoryPicker`. */
export async function fromDirectoryHandle(handle: DirectoryHandleLike): Promise<ChosenFolder> {
  const files: ChosenFile[] = [];
  const walk = async (folder: DirectoryHandleLike, prefix: string): Promise<void> => {
    for await (const child of folder.values()) {
      const path = prefix + child.name;
      if (child.kind === "directory") await walk(child, `${path}/`);
      else files.push({ path, file: await child.getFile() });
    }
  };
  await walk(handle, "");
  return sorted(handle.name, files);
}

/**
 * The files of an `<input webkitdirectory>`. Each is named from the chosen folder, whose own name
 * is the first segment and is taken off. An empty folder gives no files, and so no folder name.
 */
export function fromFileList(list: ArrayLike<RelativeFile>): ChosenFolder {
  const files: ChosenFile[] = [];
  let name: string | undefined;
  for (const file of Array.from(list)) {
    const [top, ...rest] = file.webkitRelativePath.split("/");
    if (!top || rest.length === 0)
      throw new NotAFolder("Choose a folder, not separate files, to describe.");
    if (name !== undefined && top !== name)
      throw new NotAFolder("Choose one folder at a time to describe.");
    name = top;
    files.push({ path: rest.join("/"), file });
  }
  if (name === undefined) throw new NotAFolder("The folder chosen holds no files.");
  return sorted(name, files);
}

function readAll(folder: DirectoryEntryLike): Promise<EntryLike[]> {
  const reader = folder.createReader();
  const all: EntryLike[] = [];
  // `readEntries` gives a page of entries at a time, and an empty page at the end.
  return new Promise((resolve, reject) => {
    const next = (): void =>
      reader.readEntries((page) => {
        if (page.length === 0) resolve(all);
        else {
          all.push(...page);
          next();
        }
      }, reject);
    next();
  });
}

function fileOf(entry: FileEntryLike): Promise<Blob> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

/**
 * The files under a folder dropped on the page: `entries` are the dropped items'
 * `webkitGetAsEntry()`, taken while the drop event lasts. Exactly one folder is accepted.
 */
export async function fromEntries(entries: (EntryLike | null)[]): Promise<ChosenFolder> {
  const [folder, ...others] = entries;
  if (!folder || others.length > 0 || !folder.isDirectory)
    throw new NotAFolder("Drop one folder to describe.");
  const files: ChosenFile[] = [];
  const walk = async (dir: DirectoryEntryLike, prefix: string): Promise<void> => {
    for (const child of await readAll(dir)) {
      const path = prefix + child.name;
      if (child.isDirectory) await walk(child, `${path}/`);
      else files.push({ path, file: await fileOf(child) });
    }
  };
  await walk(folder, "");
  return sorted(folder.name, files);
}
