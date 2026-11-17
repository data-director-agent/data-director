/**
 * Build the browser bundle of `dd-inventory` (README.md, Browser bundle): Pyodide, the command's
 * wheel built from this commit, and its dependencies, in one folder the app can serve from its
 * own origin, so that a scan fetches nothing from PyPI or a CDN.
 *
 *     npm run bundle            # writes dist/inventory-bundle/
 *
 * Needs `uv` and network access at build time only. Every wheel downloaded is checked against the
 * SHA-256 its lock gives: Pyodide's lock (from the pinned npm package) or the workspace's
 * (`uv export`). Downloads are kept in `.cache/wheels/`, so a rebuild needs no network.
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { parse as parseToml } from "smol-toml";

import { BUNDLE_DIR, CORE_FILES, MANIFEST, type Manifest } from "./manifest.ts";
import {
  BundleError,
  resolveBundle,
  type BundleWheel,
  type CommandWheel,
  type PyodideLock,
  type PylockPackage,
} from "./resolve.ts";

const PACKAGE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MEMBER = resolve(PACKAGE, "..");
const CACHE = join(PACKAGE, ".cache", "wheels");
const DISTRIBUTION = "data-director-inventory";

const pyodideDir = dirname(createRequire(import.meta.url).resolve("pyodide/package.json"));
const pyodideVersion = (
  JSON.parse(readFileSync(join(pyodideDir, "package.json"), "utf8")) as { version: string }
).version;
const CDN = `https://cdn.jsdelivr.net/pyodide/v${pyodideVersion}/full/`;

function sha256(data: Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

function run(command: string, args: string[]): string {
  return execFileSync(command, args, {
    cwd: MEMBER,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  });
}

/** The command's wheel, built from `inventory/` as it is now. */
function buildCommand(into: string): CommandWheel {
  const out = mkdtempSync(join(tmpdir(), "dd-inventory-wheel-"));
  run("uv", ["build", "--wheel", "--package", DISTRIBUTION, "--out-dir", out]);
  const file = readdirSync(out).find((f) => f.endsWith(".whl"));
  if (!file) throw new BundleError("uv build wrote no wheel");
  const data = readFileSync(join(out, file));
  writeFileSync(join(into, file), data);
  rmSync(out, { recursive: true, force: true });
  return { name: DISTRIBUTION, version: file.split("-")[1] ?? "", file, sha256: sha256(data) };
}

/** The command's dependencies as the workspace locks them. */
function workspacePackages(): PylockPackage[] {
  // Written to a file, not read from stdout, which uv highlights when FORCE_COLOR is set.
  const out = mkdtempSync(join(tmpdir(), "dd-inventory-lock-"));
  const lock = join(out, "pylock.toml");
  run("uv", [
    "export",
    "--format",
    "pylock.toml",
    "--package",
    DISTRIBUTION,
    "--no-dev",
    "--no-emit-workspace",
    "--frozen",
    "--quiet",
    "--output-file",
    lock,
  ]);
  const text = readFileSync(lock, "utf8");
  rmSync(out, { recursive: true, force: true });
  return (parseToml(text) as unknown as { packages: PylockPackage[] }).packages;
}

/** A wheel's bytes, from the cache or downloaded, checked against its lock's digest. */
async function fetchWheel(wheel: BundleWheel): Promise<Uint8Array> {
  const cached = join(CACHE, wheel.file);
  if (existsSync(cached)) {
    const data = readFileSync(cached);
    if (sha256(data) === wheel.sha256) return data;
  }
  const url = wheel.source === "pyodide" ? CDN + wheel.from : (wheel.from as string);
  const response = await fetch(url);
  if (!response.ok) throw new BundleError(`${url}: HTTP ${response.status}`);
  const data = new Uint8Array(await response.arrayBuffer());
  if (sha256(data) !== wheel.sha256)
    throw new BundleError(`${url}: SHA-256 does not match its lock`);
  mkdirSync(CACHE, { recursive: true });
  writeFileSync(cached, data);
  return data;
}

async function main(): Promise<void> {
  const out = join(PACKAGE, BUNDLE_DIR);
  rmSync(out, { recursive: true, force: true });
  mkdirSync(join(out, "wheels"), { recursive: true });

  const pyodideLock = JSON.parse(
    readFileSync(join(pyodideDir, "pyodide-lock.json"), "utf8"),
  ) as PyodideLock;
  const command = buildCommand(join(out, "wheels"));
  const { wheels, lock } = resolveBundle(pyodideLock, workspacePackages(), command);

  const sizes: Record<string, { bytes: number; gzip: number }> = {};
  const record = (path: string, data: Uint8Array): void => {
    sizes[path] = { bytes: data.byteLength, gzip: gzipSync(data).byteLength };
  };
  for (const wheel of wheels) {
    const path = `wheels/${wheel.file}`;
    const data =
      wheel.source === "command" ? readFileSync(join(out, path)) : await fetchWheel(wheel);
    if (wheel.source !== "command") writeFileSync(join(out, path), data);
    record(path, data);
  }
  for (const file of CORE_FILES) {
    copyFileSync(join(pyodideDir, file), join(out, file));
    record(file, readFileSync(join(out, file)));
  }
  const lockText = JSON.stringify(lock, null, 1);
  writeFileSync(join(out, "pyodide-lock.json"), lockText);
  record("pyodide-lock.json", new TextEncoder().encode(lockText));

  const manifest: Manifest = {
    pyodide: pyodideVersion,
    command: { name: command.name, version: command.version },
    entry: DISTRIBUTION,
    wheels: wheels.map(({ name, version, file, sha256, source }) => ({
      name,
      version,
      file,
      sha256,
      source,
    })),
    files: sizes,
  };
  writeFileSync(join(out, MANIFEST), JSON.stringify(manifest, null, 2) + "\n");
  const total = Object.values(sizes).reduce(
    (a, s) => ({ bytes: a.bytes + s.bytes, gzip: a.gzip + s.gzip }),
    { bytes: 0, gzip: 0 },
  );
  console.log(
    `Wrote ${out}: ${wheels.length} wheels, ${(total.bytes / 1e6).toFixed(1)} MB (${(total.gzip / 1e6).toFixed(1)} MB gzip).`,
  );
}

main().catch((error: unknown) => {
  console.error(error instanceof BundleError ? `bundle: ${error.message}` : error);
  process.exit(1);
});
