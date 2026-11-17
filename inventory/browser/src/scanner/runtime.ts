/**
 * Start Pyodide from the browser bundle, install `dd-inventory` into it, and run the command's
 * `make_inventory` over a mounted folder. The worker (`worker.ts`) uses it in a browser and the
 * parity check (`bundle/parity.ts`) in Node, so both run the command the same way.
 *
 * Pyodide's types are not imported: the package has no runtime dependency, and the app compiles
 * this source without Pyodide installed. `PyodideLike` is the little of its API used here.
 */

export interface PyodideLike {
  loadPackage(names: string, options: Record<string, unknown>): Promise<unknown>;
  runPython(code: string): unknown;
}

/** A Python callable as Pyodide hands it to JavaScript. */
type PyCallable = ((...args: unknown[]) => unknown) & { destroy?: () => void };

/** One file handled by `make_inventory`, as its `on_file` hook reports it (`FileProgress`). */
export interface FileProgress {
  path: string;
  size: number;
  done: number;
  total: number;
}

/**
 * Pyodide with the bundle's wheels installed. `indexURL` is the bundle's folder (a path in Node,
 * a URL in a browser), ending in `/`. The bundle's own lock file names only its wheels, each with
 * its SHA-256, which Pyodide checks as it installs them. `options` go to `loadPyodide` as well.
 */
export async function loadInventoryRuntime<P extends PyodideLike>(
  loadPyodide: (options: Record<string, unknown>) => Promise<P>,
  indexURL: string,
  manifest: { entry: string },
  options: Record<string, unknown> = {},
): Promise<P> {
  const pyodide = await loadPyodide({
    indexURL,
    lockFileURL: `${indexURL}pyodide-lock.json`,
    packageBaseUrl: indexURL,
    packageCacheDir: indexURL,
    stdout: () => undefined,
    stderr: () => undefined,
    ...options,
  });
  await pyodide.loadPackage(manifest.entry, {
    messageCallback: () => undefined,
    checkIntegrity: true,
  });
  return pyodide;
}

const SCAN = `
import json
from pathlib import Path
from dd_inventory import make_inventory

def _dd_scan(root, report=None):
    on_file = None
    if report is not None:
        def on_file(p):
            report(p.path, p.size, p.done, p.total)
    return json.dumps(make_inventory(Path(root), on_file=on_file))

_dd_scan
`;

/**
 * The inventory `make_inventory` writes of the folder at `root` in Pyodide's file system, as the
 * JSON text the command writes. `onFile` is called once per file, in order.
 */
export function scanFolder(
  pyodide: PyodideLike,
  root: string,
  onFile?: (progress: FileProgress) => void,
): string {
  const scan = pyodide.runPython(SCAN) as PyCallable;
  try {
    const report = onFile
      ? (path: string, size: number, done: number, total: number) =>
          onFile({ path, size, done, total })
      : undefined;
    return scan(root, report) as string;
  } finally {
    scan.destroy?.();
  }
}
