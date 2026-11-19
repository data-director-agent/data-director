/**
 * The browser scanner's Web Worker: `dd-inventory` under Pyodide, over a folder the researcher
 * chose, mounted read-only (README.md, Browser scanner). Start it as a module worker, and talk to
 * it with `startScan` (`protocol.ts`):
 *
 *     new Worker(new URL("…/scanner/worker.ts", import.meta.url), { type: "module" })
 *
 * The worker is meant to run under `default-src 'none'; script-src blob: 'wasm-unsafe-eval';
 * connect-src 'none'`, so it fetches nothing: the page hands it the bundle's bytes. Pyodide's two
 * scripts are imported from `blob:` URLs made of those bytes, and its requests for the rest are
 * answered from them (`serveFrom`). The files are mounted with Emscripten's WORKERFS, which reads
 * slices of each `File` on demand and copies none of them.
 */

import { BUNDLE_URL, serveFrom, type BundleAssets } from "./assets";
import type { ChosenFolder } from "./choose";
import type { ScanEvent, ScanRequest } from "./protocol";
import { loadInventoryRuntime, scanFolder, type PyodideLike } from "./runtime";

/** Where the chosen folder is mounted, as on disk for the command. */
const ROOT = "/data";

interface FileSystem {
  mkdirTree(path: string): void;
  mount(type: unknown, options: { blobs: { name: string; data: Blob }[] }, path: string): void;
  filesystems: { WORKERFS: unknown };
}

type Pyodide = PyodideLike & { FS: FileSystem };

interface WorkerScope {
  fetch: typeof fetch;
  postMessage(event: ScanEvent): void;
  onmessage: ((event: { data: ScanRequest }) => void) | null;
}

const scope = globalThis as unknown as WorkerScope;
const post = (event: ScanEvent): void => scope.postMessage(event);

async function importFrom(bytes: ArrayBuffer | undefined, name: string): Promise<unknown> {
  if (!bytes) throw new Error(`The scanner's bundle has no ${name}.`);
  const url = URL.createObjectURL(new Blob([bytes], { type: "text/javascript" }));
  try {
    return await import(/* @vite-ignore */ url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function start(assets: BundleAssets): Promise<Pyodide> {
  scope.fetch = serveFrom(assets.files);
  const { loadPyodide } = (await importFrom(assets.files["pyodide.mjs"], "pyodide.mjs")) as {
    loadPyodide: (options: Record<string, unknown>) => Promise<Pyodide>;
  };
  const module = (await importFrom(assets.files["pyodide.asm.mjs"], "pyodide.asm.mjs")) as {
    default: unknown;
  };
  post({ type: "stage", stage: "installing" });
  return loadInventoryRuntime(loadPyodide, BUNDLE_URL, assets.manifest, {
    createPyodideModule: module.default,
  });
}

function mount(pyodide: Pyodide, folder: ChosenFolder): void {
  const blobs = folder.files.map(({ path, file }) => ({ name: path, data: file }));
  pyodide.FS.mkdirTree(ROOT);
  pyodide.FS.mount(pyodide.FS.filesystems.WORKERFS, { blobs }, ROOT);
}

async function scan({ assets, folder }: ScanRequest): Promise<void> {
  post({ type: "stage", stage: "starting" });
  const pyodide = await start(assets);
  post({ type: "stage", stage: "reading" });
  mount(pyodide, folder);
  const inventory = scanFolder(pyodide, ROOT, (progress) =>
    post({ type: "progress", ...progress }),
  );
  post({ type: "done", inventory });
}

scope.onmessage = ({ data }) => {
  if (data.type !== "scan") return;
  scan(data).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : String(error);
    post({ type: "failed", reason: `The folder could not be described: ${detail}` });
  });
};
