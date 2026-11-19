/**
 * Check that `dd-inventory` writes the same inventory under Pyodide, from the built bundle, as it
 * does natively, on the shared sample folder (`inventory/tests/data/mixed`). Run after
 * `npm run bundle`:
 *
 *     npm run parity [-- path/to/folder]
 *
 * Exits 1, listing each difference, if the runtimes disagree beyond when each inventory was made
 * and the runtime's label in the tool version, or if anything under Pyodide asks for the network. Writes a summary of the bundle to stdout and, in
 * CI, to the job summary.
 */

import { appendFileSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { loadPyodide } from "pyodide";

import { loadInventoryRuntime, scanFolder } from "../src/scanner/runtime.ts";
import { parityProblems } from "./compare.ts";
import { BUNDLE_DIR, MANIFEST, summarise, type Manifest } from "./manifest.ts";
import { nativeInventory, PACKAGE, SAMPLE, type Inventory } from "./native.ts";

/** The inventory the same code writes under Pyodide, over the folder mounted at `/data`. */
async function pyodideInventory(
  folder: string,
  bundle: string,
  manifest: Manifest,
): Promise<Inventory> {
  const pyodide = await loadInventoryRuntime(
    (options) => loadPyodide(options),
    `${bundle}/`,
    manifest,
  );
  pyodide.FS.mkdir("/data");
  pyodide.mountNodeFS("/data", folder);
  return JSON.parse(scanFolder(pyodide, "/data")) as Inventory;
}

/**
 * Refuse every network request from here on, and keep what was asked for: the bundle must load
 * and scan from its own files alone (Pyodide reads them from disk in Node).
 */
function refuseNetwork(): string[] {
  const asked: string[] = [];
  globalThis.fetch = (input: string | URL | Request) => {
    asked.push(input instanceof Request ? input.url : String(input));
    return Promise.reject(new Error("the parity check allows no network request"));
  };
  return asked;
}

async function main(): Promise<number> {
  const folder = resolve(process.argv[2] ?? SAMPLE);
  const bundle = join(PACKAGE, BUNDLE_DIR);
  const manifest = JSON.parse(readFileSync(join(bundle, MANIFEST), "utf8")) as Manifest;
  const runtime = `pyodide.${manifest.pyodide}`;

  const native = nativeInventory(folder);
  const asked = refuseNetwork();
  const browser = await pyodideInventory(folder, bundle, manifest);
  const problems = [
    ...parityProblems(native, browser, runtime),
    ...asked.map((url) => `network request under Pyodide: ${url}`),
  ];

  const summary = summarise(manifest, String(browser.inventory_identified_with ?? "") || undefined);
  const verdict = problems.length
    ? `**The runtimes disagree** on \`${folder}\`:\n\n${problems.map((p) => `- \`${p}\``).join("\n")}\n`
    : `The inventory under Pyodide equals the command's on \`${folder}\`, apart from when it was made and \`+${runtime}\` in its tool version.\n`;
  console.log(`${summary}\n${verdict}`);
  if (process.env.GITHUB_STEP_SUMMARY)
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${summary}\n${verdict}`);
  return problems.length ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (error: unknown) => {
    console.error(error);
    process.exit(1);
  },
);
