/**
 * The inventory `dd-inventory` writes natively, through uv, from the workspace's lock: what the
 * parity check (`parity.ts`) and the browser test (`e2e/`) compare Pyodide's inventory with.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { Json } from "./compare.ts";

/** This package's folder, and the command's (`inventory/`). */
export const PACKAGE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const MEMBER = resolve(PACKAGE, "..");
/** The sample folder both runtimes describe. */
export const SAMPLE = join(MEMBER, "tests", "data", "mixed");

export type Inventory = Record<string, Json>;

export function nativeInventory(folder: string): Inventory {
  const out = mkdtempSync(join(tmpdir(), "dd-inventory-native-"));
  const file = join(out, "inventory.json");
  try {
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
      { cwd: MEMBER, stdio: ["ignore", "inherit", "inherit"] },
    );
    return JSON.parse(readFileSync(file, "utf8")) as Inventory;
  } finally {
    rmSync(out, { recursive: true, force: true });
  }
}
