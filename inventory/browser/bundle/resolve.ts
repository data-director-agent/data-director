/**
 * Which wheels the browser bundle of `dd-inventory` holds, and the lock file it installs them
 * from (README.md, Browser bundle). Pure: the build (`build.ts`) does the reading, downloading and
 * writing.
 *
 * The rule: a package Pyodide builds is taken from Pyodide's lock, with Pyodide's own
 * dependencies for it, because Pyodide tested those versions together and compiles some of them
 * (pydantic-core, PyYAML, MarkupSafe, rpds-py); any other package is the workspace lock's pure
 * Python wheel. A package built here besides the command, such as the stand-in for spaCy
 * (`spacy-stub/`), is added as it is. The command's own wheel depends on every other package, so
 * installing it installs the bundle.
 */

/** Pyodide's `pyodide-lock.json`, as much of it as the bundle reads and writes. */
export interface PyodideLock {
  info: Record<string, unknown>;
  packages: Record<string, PyodideLockPackage>;
}

export interface PyodideLockPackage {
  name: string;
  version: string;
  file_name: string;
  sha256: string;
  depends: string[];
  imports: string[];
  install_dir: string;
  package_type: string;
  [key: string]: unknown;
}

/** A package in the PEP 751 lock that `uv export --format pylock.toml` writes. */
export interface PylockPackage {
  name: string;
  version: string;
  marker?: string;
  wheels?: { url: string; size?: number; hashes: { sha256: string } }[];
}

/** The command's wheel, or another wheel built here, from this commit. */
export interface CommandWheel {
  name: string;
  version: string;
  file: string;
  sha256: string;
}

export type WheelSource = "pyodide" | "workspace" | "command";

/** One wheel in the bundle: where it comes from and how to check it. */
export interface BundleWheel {
  name: string;
  version: string;
  /** The file name under the bundle's `wheels/` folder. */
  file: string;
  sha256: string;
  source: WheelSource;
  /** Where to fetch it from: a file name under Pyodide's CDN, or a full URL; none for the command. */
  from: string | null;
}

export class BundleError extends Error {}

/** A distribution name in its normal form (PEP 503), as both locks may spell it differently. */
export function normaliseName(name: string): string {
  return name.toLowerCase().replace(/[-_.]+/g, "-");
}

/** The environment markers of Pyodide's Python, as far as the bundle's dependencies use them. */
export const PYODIDE_MARKERS: Readonly<Record<string, string>> = {
  sys_platform: "emscripten",
  platform_system: "Emscripten",
  os_name: "posix",
  platform_machine: "wasm32",
  implementation_name: "cpython",
  platform_python_implementation: "CPython",
};

const CLAUSE = /^\s*(\w+)\s*(==|!=)\s*(['"])(.*?)\3\s*$/;

/**
 * Whether a marker holds under Pyodide. Only `name == 'value'` and `name != 'value'` clauses
 * joined by `and` or `or`, without brackets, are understood; anything else fails the build, so
 * that a new kind of marker is looked at rather than guessed.
 */
export function markerHolds(marker: string | undefined): boolean {
  if (!marker?.trim()) return true;
  if (/[()]/.test(marker)) throw new BundleError(`Marker not understood: ${marker}`);
  return marker.split(/\s+or\s+/).some((any) =>
    any.split(/\s+and\s+/).every((clause) => {
      const m = CLAUSE.exec(clause);
      const value = m?.[1] === undefined ? undefined : PYODIDE_MARKERS[m[1]];
      if (!m || value === undefined) throw new BundleError(`Marker not understood: ${marker}`);
      return (value === m[4]) === (m[2] === "==");
    }),
  );
}

function isPure(file: string): boolean {
  return /-py3-none-any\.whl$|-py2\.py3-none-any\.whl$/.test(file);
}

function fromPyodide(entry: PyodideLockPackage): BundleWheel {
  return {
    name: entry.name,
    version: entry.version,
    file: entry.file_name,
    sha256: entry.sha256,
    source: "pyodide",
    from: entry.file_name,
  };
}

function fromWorkspace(pkg: PylockPackage): BundleWheel {
  const wheel = pkg.wheels?.find((w) => isPure(w.url.slice(w.url.lastIndexOf("/") + 1)));
  if (!wheel) {
    throw new BundleError(
      `${pkg.name} ${pkg.version} has no pure Python wheel and Pyodide does not build it`,
    );
  }
  return {
    name: pkg.name,
    version: pkg.version,
    file: decodeURIComponent(wheel.url.slice(wheel.url.lastIndexOf("/") + 1)),
    sha256: wheel.hashes.sha256,
    source: "workspace",
    from: wheel.url,
  };
}

/** Add a Pyodide package and, recursively, what Pyodide's lock says it depends on. */
function addFromPyodide(
  lock: PyodideLock,
  key: string,
  chosen: Map<string, BundleWheel>,
  depends: Map<string, string[]>,
): void {
  if (chosen.has(key)) return;
  const entry = lock.packages[key];
  if (!entry) throw new BundleError(`Pyodide's lock names ${key} but does not hold it`);
  chosen.set(key, fromPyodide(entry));
  depends.set(key, entry.depends);
  for (const dep of entry.depends) addFromPyodide(lock, normaliseName(dep), chosen, depends);
}

/**
 * The bundle's wheels, the command's last, and the lock file Pyodide installs them from. `built`
 * are other wheels built here, which the command's installation installs too.
 */
export function resolveBundle(
  pyodide: PyodideLock,
  workspace: PylockPackage[],
  command: CommandWheel,
  built: CommandWheel[] = [],
): { wheels: BundleWheel[]; lock: PyodideLock } {
  const chosen = new Map<string, BundleWheel>();
  const depends = new Map<string, string[]>();
  for (const wheel of built) {
    const key = normaliseName(wheel.name);
    if (key in pyodide.packages || workspace.some((p) => normaliseName(p.name) === key)) {
      throw new BundleError(`${wheel.name} is built here and also locked elsewhere`);
    }
    chosen.set(key, { ...wheel, source: "command", from: null });
    depends.set(key, []);
  }
  for (const pkg of workspace) {
    if (!markerHolds(pkg.marker)) continue;
    const key = normaliseName(pkg.name);
    if (key in pyodide.packages) addFromPyodide(pyodide, key, chosen, depends);
    else if (!chosen.has(key)) {
      chosen.set(key, fromWorkspace(pkg));
      depends.set(key, []);
    }
  }
  const keys = [...chosen.keys()].sort();
  const commandKey = normaliseName(command.name);
  const wheels: BundleWheel[] = keys.map((k) => chosen.get(k) as BundleWheel);
  wheels.push({ ...command, source: "command", from: null });
  depends.set(commandKey, keys);

  const packages: Record<string, PyodideLockPackage> = {};
  for (const [i, w] of wheels.entries()) {
    const key = i < keys.length ? (keys[i] as string) : commandKey;
    const original = w.source === "pyodide" ? pyodide.packages[key] : undefined;
    packages[key] = {
      ...(original ?? {
        imports: [],
        install_dir: "site",
        package_type: "package",
        unvendored_tests: false,
      }),
      name: w.name,
      version: w.version,
      file_name: `wheels/${w.file}`,
      sha256: w.sha256,
      depends: depends.get(key) ?? [],
    };
  }
  return { wheels, lock: { info: pyodide.info, packages } };
}
