import type { ChosenFolder, ScanEvent, WorkerLike } from "@data-director/inventory";

import { makeScanner } from "./scanner";

const BASE = "https://app.example/inventory-bundle/";
const MANIFEST = { pyodide: "314.0.8", entry: "data-director-inventory", files: { "a.whl": {} } };
const FOLDER: ChosenFolder = { name: "survey", files: [{ path: "a.csv", file: new Blob(["x"]) }] };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** A fetcher serving the bundle, counting what it is asked for. */
function bundleServer(manifest: unknown = MANIFEST) {
  const asked: string[] = [];
  const fetcher = vi.fn(async (url: string) => {
    asked.push(url.slice(BASE.length));
    if (url === `${BASE}manifest.json`) return json(manifest);
    if (url === `${BASE}a.whl`) return new Response(new Uint8Array([1, 2, 3]));
    return new Response(null, { status: 404 });
  });
  return { fetcher, asked };
}

/** A worker that answers each scan with `reply`, once it has been posted the request. */
function fakeWorker(reply: ScanEvent[] = [{ type: "done", inventory: "{}" }]) {
  const worker: WorkerLike & { posted: unknown[]; terminated: boolean } = {
    posted: [],
    terminated: false,
    onmessage: null,
    onerror: null,
    postMessage(message: unknown) {
      this.posted.push(message);
      queueMicrotask(() => {
        for (const data of reply) this.onmessage?.call(this as never, { data } as MessageEvent);
      });
    },
    terminate() {
      this.terminated = true;
    },
  };
  return worker;
}

describe("makeScanner", () => {
  it("is available when the deployment serves the bundle's manifest, asking once", async () => {
    const { fetcher } = bundleServer();
    const scanner = makeScanner({ base: BASE, fetcher });
    expect(await scanner.available()).toBe(true);
    expect(await scanner.available()).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["not served", async () => new Response(null, { status: 404 })],
    ["the shell's page, not a manifest", async () => new Response("<!doctype html>")],
    ["some other JSON", async () => json({ hello: "world" })],
    ["unreachable", async () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("is not available when the manifest is %s", async (_, fetcher) => {
    expect(await makeScanner({ base: BASE, fetcher }).available()).toBe(false);
  });

  it("asks again after a no, so one failed fetch does not hide the browser route for good", async () => {
    const { fetcher: served } = bundleServer();
    let up = false;
    const fetcher = vi.fn(async (url: string) => {
      if (!up) throw new TypeError("Failed to fetch");
      return served(url);
    });
    const scanner = makeScanner({ base: BASE, fetcher });
    expect(await scanner.available()).toBe(false);
    up = true;
    expect(await scanner.available()).toBe(true);
    expect(await scanner.available()).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("fetches the bundle once and gives each scan a fresh worker", async () => {
    const { fetcher, asked } = bundleServer();
    const workers = [fakeWorker(), fakeWorker()];
    const scanner = makeScanner({
      base: BASE,
      fetcher,
      makeWorker: () => {
        const worker = workers.shift();
        if (!worker) throw new Error("a third worker");
        return worker;
      },
    });
    const events: ScanEvent[] = [];
    const first = scanner.scan(FOLDER, (e) => events.push(e));
    expect(await first.outcome).toEqual({ status: "done", inventory: "{}" });
    expect(await scanner.scan(FOLDER, () => undefined).outcome).toMatchObject({ status: "done" });
    expect(asked).toEqual(["manifest.json", "a.whl"]);
    expect(workers).toEqual([]);
    expect(events).toEqual([{ type: "done", inventory: "{}" }]);
  });

  it("hands the worker the bundle and the folder, and nothing else", async () => {
    const worker = fakeWorker();
    const scanner = makeScanner({
      base: BASE,
      fetcher: bundleServer().fetcher,
      makeWorker: () => worker,
    });
    await scanner.scan(FOLDER, () => undefined).outcome;
    expect(worker.posted).toEqual([
      {
        type: "scan",
        folder: FOLDER,
        assets: { manifest: MANIFEST, files: { "a.whl": expect.any(ArrayBuffer) } },
      },
    ]);
    expect(worker.terminated).toBe(true);
  });

  it("fails a scan whose bundle cannot be fetched, and tries again on the next", async () => {
    let served = false;
    const fetcher = vi.fn(async (url: string) =>
      served ? bundleServer().fetcher(url) : new Response(null, { status: 503 }),
    );
    const scanner = makeScanner({ base: BASE, fetcher, makeWorker: () => fakeWorker() });
    const failed = await scanner.scan(FOLDER, () => undefined).outcome;
    expect(failed.status).toBe("failed");
    served = true;
    expect((await scanner.scan(FOLDER, () => undefined).outcome).status).toBe("done");
  });

  it("starts no worker when cancelled while the bundle is fetched", async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    const { fetcher: serve } = bundleServer();
    const fetcher = async (url: string) => {
      await held;
      return serve(url);
    };
    const makeWorker = vi.fn(() => fakeWorker());
    const handle = makeScanner({ base: BASE, fetcher, makeWorker }).scan(FOLDER, () => undefined);
    handle.cancel();
    expect(await handle.outcome).toEqual({ status: "cancelled" });
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(makeWorker).not.toHaveBeenCalled();
  });

  it("ends the worker when a running scan is cancelled", async () => {
    const worker = fakeWorker([{ type: "stage", stage: "starting" }]);
    const scanner = makeScanner({
      base: BASE,
      fetcher: bundleServer().fetcher,
      makeWorker: () => worker,
    });
    const handle = scanner.scan(FOLDER, () => handle.cancel());
    expect(await handle.outcome).toEqual({ status: "cancelled" });
    expect(worker.terminated).toBe(true);
  });
});
