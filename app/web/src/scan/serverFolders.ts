/**
 * Folders on the machine the app runs on, which a local install may describe
 * (docs/specs/app.md, Make an inventory; `dd_app.folder_scan`). The app lists only the folders its
 * operator named in `DD_INVENTORY_FOLDERS` and their subfolders, by name, and describes one with
 * `dd-inventory` itself. It records nothing: the inventory comes back to be checked like any
 * other. A deployment that names no folder, as the shared one does, offers none of this.
 */

import { json } from "../http";

export interface FolderListing {
  root: string;
  path: string;
  folders: string[];
}

export interface ServerFolders {
  /** Whether this deployment describes folders on its own machine. Asked once; kept. */
  available(): Promise<boolean>;
  /** The folders the deployment names. */
  roots(signal?: AbortSignal): Promise<string[]>;
  /** The subfolders of `path` under `root`, by name. */
  list(root: string, path: string, signal?: AbortSignal): Promise<FolderListing>;
  /** The inventory of `path` under `root`, as JSON text. */
  describe(root: string, path: string, signal?: AbortSignal): Promise<string>;
}

type Fetch = typeof fetch;

/** Whether `GET /api/about` says the deployment describes folders on its own machine. */
async function offersFolders(fetcher: Fetch): Promise<boolean> {
  try {
    const response = await fetcher("/api/about");
    if (!response.ok) return false;
    const about = (await response.json()) as { server_folders?: unknown };
    return about.server_folders === true;
  } catch {
    return false;
  }
}

export function makeServerFolders(fetcher: Fetch = (...args) => fetch(...args)): ServerFolders {
  let available: Promise<boolean> | undefined;
  const init = (signal?: AbortSignal) => (signal ? { signal } : {});
  return {
    available: () => (available ??= offersFolders(fetcher)),
    async roots(signal) {
      const found = await json<{ roots: string[] }>(await fetcher("/api/folders", init(signal)));
      return found.roots;
    },
    async list(root, path, signal) {
      const query = new URLSearchParams({ root, path });
      return json(await fetcher(`/api/folders?${query.toString()}`, init(signal)));
    },
    async describe(root, path, signal) {
      const inventory = await json<unknown>(
        await fetcher("/api/folders/inventory", {
          ...init(signal),
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ root, path }),
        }),
      );
      return JSON.stringify(inventory, null, 2);
    },
  };
}

let shared: ServerFolders | undefined;

/** The page's server folders, made when first asked for. */
export function pageServerFolders(): ServerFolders {
  shared ??= makeServerFolders();
  return shared;
}

/** Put `folders` in place of the page's, as the unit tests do. */
export function setPageServerFolders(folders: ServerFolders): void {
  shared = folders;
}
