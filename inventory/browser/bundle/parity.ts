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

import { execFileSync } from "node:child_process";
import { appendFileSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "pyodide";

import { parityProblems, type Json } from "./compare.ts";
import { loadInventoryRuntime } from "./load.ts";
import { BUNDLE_DIR, MANIFEST, summarise, type Manifest } from "./manifest.ts";

const PACKAGE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MEMBER = resolve(PACKAGE, "..");
const SAMPLE = join(MEMBER, "tests", "data", "mixed");

type Inventory = Record<string, Json>;

/** The inventory the command writes natively, through uv, from the workspace's lock. */
function nativeInventory(folder: string): Inventory {
  const out = mkdtempSync(join(tmpdir(), "dd-inventory-native-"));
  const file = join(out, "inventory.json");
  execFileSync(
    "uv",
    [
      "run",
      "--frozen",
      "--quiet",
      "--package",
      "data-director-inventory",
      "dd-inventory",
      folder,
      "-o",
      file,
    ],
    {
      cwd: MEMBER,
      stdio: ["ignore", "inherit", "inherit"],
    },
  );
  const inventory = JSON.parse(readFileSync(file, "utf8")) as Inventory;
  rmSync(out, { recursive: true, force: true });
  return inventory;
}

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
  const text = pyodide.runPython(
    "import json\nfrom pathlib import Path\nfrom dd_inventory import make_inventory\n" +
      'json.dumps(make_inventory(Path("/data")))',
  ) as string;
  return JSON.parse(text) as Inventory;
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
