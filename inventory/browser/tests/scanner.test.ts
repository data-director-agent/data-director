import {
  BUNDLE_URL,
  canPickDirectory,
  fetchBundle,
  fromDirectoryHandle,
  fromEntries,
  fromFileList,
  matchesIntegrity,
  NotAFolder,
  serveFrom,
  startScan,
  type BundleAssets,
  type DirectoryEntryLike,
  type DirectoryHandleLike,
  type EntryLike,
  type FileHandleLike,
  type RelativeFile,
  type ScanEvent,
  type WorkerLike,
} from "../src";
import { loadInventoryRuntime, scanFolder, type PyodideLike } from "../src/scanner/runtime";

const text = (s: string): Blob => new Blob([s]);
const paths = (folder: { files: { path: string }[] }): string[] => folder.files.map((f) => f.path);

/** A folder tree as nested objects: a string is a file's content, an object a folder. */
interface Tree {
  [name: string]: string | Tree;
}

const TREE: Tree = {
  "b.csv": "b",
  ".DS_Store": "",
  tables: { "a.tsv": "a", deep: { "c.txt": "c" } },
};

function handle(name: string, tree: Tree): DirectoryHandleLike {
  return {
    kind: "directory",
    name,
    async *values() {
      for (const [child, value] of Object.entries(tree))
        yield typeof value === "string"
          ? ({ kind: "file", name: child, getFile: async () => text(value) } as FileHandleLike)
          : handle(child, value);
    },
  };
}

/** A dropped folder's entry, whose reader pages its entries two at a time, as browsers page. */
function entry(name: string, tree: Tree): DirectoryEntryLike {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader() {
      const children: EntryLike[] = Object.entries(tree).map(([child, value]) =>
        typeof value === "string"
          ? { isFile: true, isDirectory: false, name: child, file: (ok) => ok(text(value)) }
          : entry(child, value),
      );
      return { readEntries: (ok) => ok(children.splice(0, 2)) };
    },
  };
}

function relative(path: string): RelativeFile {
  return Object.assign(text(path), { webkitRelativePath: path });
}

describe("choosing a folder", () => {
  const expected = [".DS_Store", "b.csv", "tables/a.tsv", "tables/deep/c.txt"];

  it("walks a picked directory, hidden files included, sorted by path", async () => {
    const folder = await fromDirectoryHandle(handle("survey", TREE));
    expect(folder.name).toBe("survey");
    expect(paths(folder)).toEqual(expected);
    expect(await folder.files[1]?.file.text()).toBe("b");
  });

  it("walks a dropped folder through every page of its entries", async () => {
    const folder = await fromEntries([entry("survey", TREE)]);
    expect(folder.name).toBe("survey");
    expect(paths(folder)).toEqual(expected);
  });

  it("refuses a drop that is not exactly one folder", async () => {
    const file: EntryLike = {
      isFile: true,
      isDirectory: false,
      name: "a",
      file: (ok) => ok(text("")),
    };
    await expect(fromEntries([file])).rejects.toBeInstanceOf(NotAFolder);
    await expect(fromEntries([entry("a", {}), entry("b", {})])).rejects.toBeInstanceOf(NotAFolder);
    await expect(fromEntries([null])).rejects.toBeInstanceOf(NotAFolder);
  });

  it("passes on a failure to read a dropped folder", async () => {
    const broken: DirectoryEntryLike = {
      ...entry("survey", {}),
      createReader: () => ({ readEntries: (_ok, fail) => fail(new Error("gone")) }),
    };
    await expect(fromEntries([broken])).rejects.toThrow("gone");
  });

  it("names a webkitdirectory input's files from inside the chosen folder", () => {
    const list = ["survey/tables/a.tsv", "survey/b.csv", "survey/.DS_Store"].map(relative);
    const folder = fromFileList(list);
    expect(folder.name).toBe("survey");
    expect(paths(folder)).toEqual([".DS_Store", "b.csv", "tables/a.tsv"]);
  });

  it("refuses separate files, two folders, or none", () => {
    expect(() => fromFileList([relative("a.csv")])).toThrow(NotAFolder);
    expect(() => fromFileList(["x/a", "y/b"].map(relative))).toThrow(NotAFolder);
    expect(() => fromFileList([])).toThrow(NotAFolder);
  });

  it("knows whether the directory picker is offered", () => {
    expect(canPickDirectory({ showDirectoryPicker: () => undefined })).toBe(true);
    expect(canPickDirectory({})).toBe(false);
  });
});

const bytes = (s: string): ArrayBuffer => new TextEncoder().encode(s).buffer as ArrayBuffer;

async function sri(s: string, algorithm = "SHA-256", name = "sha256"): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest(algorithm, bytes(s)));
  return `${name}-${btoa(String.fromCharCode(...digest))}`;
}

describe("the bundle's files", () => {
  it("fetches the manifest and every file it lists", async () => {
    const served: Record<string, string> = {
      "manifest.json": JSON.stringify({
        pyodide: "1",
        entry: "data-director-inventory",
        files: { "pyodide.mjs": {}, "wheels/a.whl": {} },
      }),
      "pyodide.mjs": "export {}",
      "wheels/a.whl": "wheel",
    };
    const asked: string[] = [];
    const assets = await fetchBundle("/b/", async (url) => {
      asked.push(url);
      const body = served[url.slice(3)];
      return new Response(body ?? null, { status: body === undefined ? 404 : 200 });
    });
    expect(Object.keys(assets.files).sort()).toEqual(["pyodide.mjs", "wheels/a.whl"]);
    expect(new TextDecoder().decode(assets.files["wheels/a.whl"])).toBe("wheel");
    expect(asked).toContain("/b/manifest.json");
    await expect(
      fetchBundle("/c/", async () => new Response(null, { status: 404 })),
    ).rejects.toThrow("manifest.json");
  });

  it("checks subresource integrity", async () => {
    expect(await matchesIntegrity(bytes("a"), await sri("a"))).toBe(true);
    expect(await matchesIntegrity(bytes("a"), await sri("a", "SHA-384", "sha384"))).toBe(true);
    expect(await matchesIntegrity(bytes("a"), `md5-x ${await sri("a")}`)).toBe(true);
    expect(await matchesIntegrity(bytes("a"), await sri("b"))).toBe(false);
    expect(await matchesIntegrity(bytes("a"), "md5-abc")).toBe(false);
  });

  it("serves the bundle from memory and refuses every other request", async () => {
    const serve = serveFrom({ "pyodide.asm.wasm": bytes("wasm"), "wheels/a.whl": bytes("wheel") });
    const wasm = await serve(`${BUNDLE_URL}pyodide.asm.wasm`);
    expect(wasm.headers.get("Content-Type")).toBe("application/wasm");
    expect(await wasm.text()).toBe("wasm");
    const wheel = await serve(new URL(`${BUNDLE_URL}wheels/a.whl`), {
      integrity: await sri("wheel"),
    });
    expect(await wheel.text()).toBe("wheel");
    // Served twice: each response has its own copy of the bytes.
    expect(await (await serve(new Request(`${BUNDLE_URL}wheels/a.whl`))).text()).toBe("wheel");
    await expect(
      serve(`${BUNDLE_URL}wheels/a.whl`, { integrity: await sri("other") }),
    ).rejects.toThrow(TypeError);
    await expect(serve(`${BUNDLE_URL}missing.whl`)).rejects.toThrow(TypeError);
    await expect(serve("https://example.org/upload")).rejects.toThrow(TypeError);
  });
});

class FakeWorker implements WorkerLike {
  onmessage: WorkerLike["onmessage"] = null;
  onerror: WorkerLike["onerror"] = null;
  posted: unknown[] = [];
  terminated = false;
  postMessage(message: unknown): void {
    this.posted.push(message);
  }
  terminate(): void {
    this.terminated = true;
  }
  say(event: ScanEvent): void {
    this.onmessage?.call(this as unknown as Worker, { data: event } as MessageEvent<ScanEvent>);
  }
  fail(): void {
    this.onerror?.call(this as unknown as Worker, {} as ErrorEvent);
  }
}

describe("a scan", () => {
  const assets: BundleAssets = { manifest: { pyodide: "1", entry: "x", files: {} }, files: {} };
  const folder = { name: "survey", files: [] };

  it("hands the worker the bundle and folder, passes events on, and ends with the inventory", async () => {
    const worker = new FakeWorker();
    const events: ScanEvent[] = [];
    const scan = startScan(worker, assets, folder, (e) => events.push(e));
    expect(worker.posted).toEqual([{ type: "scan", assets, folder }]);
    worker.say({ type: "stage", stage: "starting" });
    worker.say({ type: "progress", path: "a", size: 1, done: 1, total: 1 });
    worker.say({ type: "done", inventory: "{}" });
    expect(await scan.outcome).toEqual({ status: "done", inventory: "{}" });
    expect(events.map((e) => e.type)).toEqual(["stage", "progress", "done"]);
    expect(worker.terminated).toBe(true);
  });

  it("ends with the worker's reason when it fails", async () => {
    const worker = new FakeWorker();
    const scan = startScan(worker, assets, folder);
    worker.say({ type: "failed", reason: "No." });
    expect(await scan.outcome).toEqual({ status: "failed", reason: "No." });
  });

  it("ends as failed when the worker itself errs", async () => {
    const worker = new FakeWorker();
    const scan = startScan(worker, assets, folder);
    worker.fail();
    expect(await scan.outcome).toMatchObject({ status: "failed" });
    expect(worker.terminated).toBe(true);
  });

  it("ends the worker when cancelled, and ignores it afterwards", async () => {
    const worker = new FakeWorker();
    const events: ScanEvent[] = [];
    const scan = startScan(worker, assets, folder, (e) => events.push(e));
    scan.cancel();
    expect(await scan.outcome).toEqual({ status: "cancelled" });
    expect(worker.terminated).toBe(true);
    expect(worker.onmessage).toBeNull();
    expect(events).toEqual([]);
  });
});

describe("the runtime", () => {
  it("loads the bundle's lock and installs the command's package", async () => {
    const loaded: Record<string, unknown>[] = [];
    const packages: string[] = [];
    const fake: PyodideLike = {
      loadPackage: async (name) => void packages.push(name),
      runPython: () => undefined,
    };
    const pyodide = await loadInventoryRuntime(
      async (options) => (loaded.push(options), fake),
      "https://b.invalid/",
      { entry: "data-director-inventory" },
      { createPyodideModule: "module" },
    );
    expect(pyodide).toBe(fake);
    expect(loaded[0]).toMatchObject({
      indexURL: "https://b.invalid/",
      lockFileURL: "https://b.invalid/pyodide-lock.json",
      createPyodideModule: "module",
    });
    expect(packages).toEqual(["data-director-inventory"]);
  });

  it("runs make_inventory over the mount and reports each file", () => {
    let destroyed = false;
    const scan = Object.assign(
      (root: string, report?: (...args: unknown[]) => void) => {
        report?.("a.csv", 3, 1, 1);
        return JSON.stringify({ root });
      },
      { destroy: () => (destroyed = true) },
    );
    const pyodide: PyodideLike = { loadPackage: async () => undefined, runPython: () => scan };
    const progress: unknown[] = [];
    expect(scanFolder(pyodide, "/data", (p) => progress.push(p))).toBe('{"root":"/data"}');
    expect(progress).toEqual([{ path: "a.csv", size: 3, done: 1, total: 1 }]);
    expect(destroyed).toBe(true);
    expect(scanFolder(pyodide, "/data")).toBe('{"root":"/data"}');
  });
});
