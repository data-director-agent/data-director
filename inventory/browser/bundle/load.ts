/**
 * Start Pyodide from the browser bundle and install `dd-inventory` into it, with nothing fetched
 * from beyond the bundle. The parity check uses it in Node; the browser worker (#554) is to use
 * it with assets the page has fetched.
 */

import type { PyodideAPI } from "pyodide";

import type { Manifest } from "./manifest.ts";

/**
 * Pyodide with the bundle's wheels installed. `indexURL` is the bundle's folder (a path in Node,
 * a URL in a browser), ending in `/`. The bundle's own lock file names only its wheels, each with
 * its SHA-256, which Pyodide checks as it installs them.
 */
export async function loadInventoryRuntime(
  loadPyodide: (options: Record<string, unknown>) => Promise<PyodideAPI>,
  indexURL: string,
  manifest: Manifest,
): Promise<PyodideAPI> {
  const pyodide = await loadPyodide({
    indexURL,
    lockFileURL: `${indexURL}pyodide-lock.json`,
    packageBaseUrl: indexURL,
    packageCacheDir: indexURL,
    stdout: () => undefined,
    stderr: () => undefined,
  });
  await pyodide.loadPackage(manifest.entry, {
    messageCallback: () => undefined,
    checkIntegrity: true,
  });
  return pyodide;
}
