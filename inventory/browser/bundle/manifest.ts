/**
 * What the browser bundle holds (`manifest.json`, written by `build.ts`) and what is said about
 * it in CI's job summary. Pure.
 */

import type { WheelSource } from "./resolve.ts";

/** Where the build writes the bundle, under this package. */
export const BUNDLE_DIR = "dist/inventory-bundle";
export const MANIFEST = "manifest.json";

/** Pyodide's own files the bundle serves, from the pinned npm package. */
export const CORE_FILES = [
  "pyodide.mjs",
  "pyodide.asm.mjs",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
] as const;

export interface Manifest {
  pyodide: string;
  command: { name: string; version: string };
  /** The package whose installation installs the rest (`loadPackage(entry)`). */
  entry: string;
  /** The licence notices (`notices.ts`), beside the manifest; not in `files`, as no scan reads them. */
  notices: string;
  wheels: { name: string; version: string; file: string; sha256: string; source: WheelSource }[];
  /** Every file in the bundle, by its path in it, with its size raw and gzipped. */
  files: Record<string, { bytes: number; gzip: number }>;
}

function megabytes(bytes: number): string {
  return `${(bytes / 1e6).toFixed(1)} MB`;
}

/** A Markdown summary of the bundle and of the parity check's inventory, for CI's job summary. */
export function summarise(manifest: Manifest, identifiedWith: string | undefined): string {
  const sizes = Object.values(manifest.files);
  const bytes = sizes.reduce((a, s) => a + s.bytes, 0);
  const gzip = sizes.reduce((a, s) => a + s.gzip, 0);
  const wheels = manifest.wheels.reduce<Record<WheelSource, number>>(
    (a, w) => ({ ...a, [w.source]: a[w.source] + 1 }),
    { pyodide: 0, workspace: 0, command: 0 },
  );
  const fido = manifest.wheels.find((w) => w.name === "opf-fido")?.version ?? "absent";
  return [
    "## Inventory browser bundle",
    "",
    "| | |",
    "| --- | --- |",
    `| Pyodide | ${manifest.pyodide} |`,
    `| ${manifest.command.name} | ${manifest.command.version} |`,
    `| fido | ${fido} |`,
    `| Identified with | ${identifiedWith ?? "not recorded"} |`,
    `| Wheels | ${manifest.wheels.length}: ${wheels.pyodide} from Pyodide, ${wheels.workspace} from the workspace lock, ${wheels.command} built |`,
    `| Size | ${megabytes(bytes)}, ${megabytes(gzip)} gzip |`,
    "",
  ].join("\n");
}
