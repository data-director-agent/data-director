import { differences, parityProblems } from "../bundle/compare";
import { summarise, type Manifest } from "../bundle/manifest";
import {
  BundleError,
  markerHolds,
  normaliseName,
  resolveBundle,
  type PyodideLock,
  type PyodideLockPackage,
  type PylockPackage,
} from "../bundle/resolve";

function entry(
  name: string,
  version: string,
  depends: string[] = [],
  file?: string,
): PyodideLockPackage {
  return {
    name,
    version,
    file_name: file ?? `${name.replace(/-/g, "_")}-${version}-py3-none-any.whl`,
    sha256: `sha-${name}`,
    depends,
    imports: [name.replace(/-/g, "_")],
    install_dir: "site",
    package_type: "package",
    unvendored_tests: false,
  };
}

const pyodideLock: PyodideLock = {
  info: { python: "3.14.2" },
  packages: {
    pydantic: entry("pydantic", "2.12.5", ["pydantic_core", "typing-extensions"]),
    "pydantic-core": entry(
      "pydantic_core",
      "2.41.5",
      ["typing-extensions"],
      "pydantic_core-2.41.5-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
    ),
    "typing-extensions": entry("typing-extensions", "4.15.0"),
    numpy: entry("numpy", "2.3.0"),
  },
};

function pylock(name: string, version: string, files: string[], marker?: string): PylockPackage {
  return {
    name,
    version,
    ...(marker ? { marker } : {}),
    wheels: files.map((f) => ({
      url: `https://files.example/${f}`,
      hashes: { sha256: `ws-${f}` },
    })),
  };
}

const workspace: PylockPackage[] = [
  pylock("pydantic", "2.14.3", ["pydantic-2.14.3-py3-none-any.whl"]),
  pylock("pydantic-core", "2.50.4", ["pydantic_core-2.50.4-cp314-cp314-manylinux.whl"]),
  pylock("opf-fido", "1.6.1", ["opf_fido-1.6.1-py3-none-any.whl"]),
  pylock("colorama", "0.4.6", ["colorama-0.4.6-py2.py3-none-any.whl"], "sys_platform == 'win32'"),
];

const command = {
  name: "data-director-inventory",
  version: "0.1.0a4",
  file: "data_director_inventory-0.1.0a4-py3-none-any.whl",
  sha256: "sha-command",
};

describe("resolveBundle", () => {
  const { wheels, lock } = resolveBundle(pyodideLock, workspace, command);
  const byName = new Map(wheels.map((w) => [normaliseName(w.name), w]));

  it("takes a package Pyodide builds, and its dependencies, from Pyodide's lock", () => {
    expect(byName.get("pydantic")).toMatchObject({ source: "pyodide", version: "2.12.5" });
    expect(byName.get("pydantic-core")).toMatchObject({ source: "pyodide", version: "2.41.5" });
    expect(byName.get("typing-extensions")?.source).toBe("pyodide");
  });

  it("takes any other package's pure Python wheel from the workspace lock", () => {
    expect(byName.get("opf-fido")).toMatchObject({
      source: "workspace",
      file: "opf_fido-1.6.1-py3-none-any.whl",
      sha256: "ws-opf_fido-1.6.1-py3-none-any.whl",
    });
  });

  it("leaves out packages whose markers do not hold under Pyodide, and Pyodide's unused ones", () => {
    expect(byName.has("colorama")).toBe(false);
    expect(byName.has("numpy")).toBe(false);
  });

  it("writes a lock of the bundle's wheels alone, the command depending on every other", () => {
    expect(Object.keys(lock.packages).sort()).toEqual([...byName.keys()].sort());
    expect(lock.info).toEqual(pyodideLock.info);
    for (const pkg of Object.values(lock.packages)) {
      expect(pkg.file_name.startsWith("wheels/")).toBe(true);
      expect(pkg.sha256).toBeTruthy();
    }
    const others = [...byName.keys()].filter((k) => k !== "data-director-inventory");
    expect([...(lock.packages["data-director-inventory"]?.depends ?? [])].sort()).toEqual(
      others.sort(),
    );
    expect(lock.packages["pydantic"]?.depends).toEqual(["pydantic_core", "typing-extensions"]);
    expect(wheels.at(-1)?.source).toBe("command");
  });

  it("adds a wheel built here, such as the stand-in for spaCy, for the command to install", () => {
    const stub = { name: "dd-spacy-stub", version: "1.0.0", file: "stub.whl", sha256: "sha-stub" };
    const built = resolveBundle(pyodideLock, workspace, command, [stub]);
    const names = built.wheels.map((w) => normaliseName(w.name));
    expect(names).toContain("dd-spacy-stub");
    expect(built.lock.packages["data-director-inventory"]?.depends).toContain("dd-spacy-stub");
    expect(built.wheels.at(-1)?.name).toBe(command.name);
  });

  it("fails when a wheel built here is also locked elsewhere", () => {
    const clash = { name: "opf_fido", version: "0.0.0", file: "fido.whl", sha256: "sha" };
    expect(() => resolveBundle(pyodideLock, workspace, command, [clash])).toThrow(BundleError);
  });

  it("fails when a package has no pure wheel and Pyodide does not build it", () => {
    const compiled = [pylock("lxml", "6.0.0", ["lxml-6.0.0-cp314-cp314-manylinux.whl"])];
    expect(() => resolveBundle(pyodideLock, compiled, command)).toThrow(BundleError);
  });

  it("fails when Pyodide's lock names a dependency it does not hold", () => {
    const broken: PyodideLock = {
      info: {},
      packages: { pydantic: entry("pydantic", "2.12.5", ["missing"]) },
    };
    expect(() => resolveBundle(broken, [workspace[0] as PylockPackage], command)).toThrow(
      BundleError,
    );
  });
});

describe("markerHolds", () => {
  it.each([
    [undefined, true],
    ["", true],
    ["sys_platform == 'win32'", false],
    ["sys_platform != 'win32'", true],
    ["sys_platform == 'win32' or os_name == \"posix\"", true],
    ["sys_platform == 'emscripten' and platform_machine != 'wasm32'", false],
  ])("%s holds: %s", (marker, holds) => {
    expect(markerHolds(marker)).toBe(holds);
  });

  it.each(["python_version < '3.15'", "(sys_platform == 'win32')", "extra == 'x'"])(
    "refuses a marker it does not understand: %s",
    (marker) => {
      expect(() => markerHolds(marker)).toThrow(BundleError);
    },
  );
});

describe("parity", () => {
  const native = {
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0a4",
    inventory_made_at: "2026-11-17T10:00:00+00:00",
    inventory_files: [{ file_path: "a.csv", file_fields: [{ name: "x", field_type: "integer" }] }],
  };

  it("accepts inventories that differ only in when they were made and the runtime label", () => {
    const browser = {
      ...native,
      inventory_tool_version: "0.1.0a4+pyodide.314.0.8",
      inventory_made_at: "2026-11-17T11:00:00+00:00",
    };
    expect(parityProblems(native, browser, "pyodide.314.0.8")).toEqual([]);
  });

  it("reports a missing runtime label and every other difference by path", () => {
    const browser = {
      ...native,
      inventory_files: [{ file_path: "a.csv", file_fields: [{ name: "x", field_type: "number" }] }],
      inventory_limitations: ["one more"],
    };
    const problems = parityProblems(native, browser, "pyodide.314.0.8");
    expect(problems).toHaveLength(3);
    expect(problems.some((p) => p.startsWith("$.inventory_tool_version"))).toBe(true);
    expect(
      problems.some((p) => p.startsWith("$.inventory_files[0].file_fields[0].field_type")),
    ).toBe(true);
    expect(problems.some((p) => p.startsWith("$.inventory_limitations"))).toBe(true);
  });

  it("compares lists element by element, a missing element as null", () => {
    expect(differences([1, 2], [1])).toEqual(["$[1]: 2 → null"]);
    expect(differences({ a: [1] }, { a: [1] })).toEqual([]);
  });
});

describe("summarise", () => {
  const manifest: Manifest = {
    pyodide: "314.0.8",
    command: { name: "data-director-inventory", version: "0.1.0a4" },
    entry: "data-director-inventory",
    notices: "NOTICES.md",
    wheels: [
      { name: "opf-fido", version: "1.6.1", file: "f.whl", sha256: "x", source: "workspace" },
      { name: "pydantic", version: "2.12.5", file: "p.whl", sha256: "y", source: "pyodide" },
      {
        name: "data-director-inventory",
        version: "0.1.0a4",
        file: "d.whl",
        sha256: "z",
        source: "command",
      },
    ],
    files: {
      "a.whl": { bytes: 2_000_000, gzip: 1_000_000 },
      "b.wasm": { bytes: 3_000_000, gzip: 500_000 },
    },
  };

  it("names the versions and sizes that a change to the bundle would move", () => {
    const text = summarise(manifest, "fido 1.6.1 with PRONOM signatures v109");
    for (const fact of [
      "314.0.8",
      "0.1.0a4",
      "1.6.1",
      "PRONOM signatures v109",
      "5.0 MB",
      "1.5 MB",
    ]) {
      expect(text).toContain(fact);
    }
  });

  it("says when fido or the signatures are not known", () => {
    const text = summarise({ ...manifest, wheels: [] }, undefined);
    expect(text).toContain("absent");
    expect(text).toContain("not recorded");
  });
});
