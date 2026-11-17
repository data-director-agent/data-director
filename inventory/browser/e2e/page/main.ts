/**
 * The page the browser test drives (`e2e/scan.spec.ts`): what the app is to do, without the app.
 * Choosing a folder starts a scan in a fresh worker; the test reads `window.scan`.
 */

import {
  fetchBundle,
  fromFileList,
  startScan,
  type RelativeFile,
  type ScanEvent,
  type ScanHandle,
  type ScanOutcome,
} from "../../src/index.ts";

declare global {
  interface Window {
    scan?: { events: ScanEvent[]; handle: ScanHandle; outcome?: ScanOutcome };
  }
}

const input = document.querySelector<HTMLInputElement>("#folder");

input?.addEventListener("change", () => {
  const folder = fromFileList(input.files as unknown as ArrayLike<RelativeFile>);
  void fetchBundle(new URL("inventory-bundle/", document.baseURI).href).then((assets) => {
    const worker = new Worker(new URL("../../src/scanner/worker.ts", import.meta.url), {
      type: "module",
    });
    const events: ScanEvent[] = [];
    const handle = startScan(worker, assets, folder, (event) => events.push(event));
    const scan: NonNullable<Window["scan"]> = { events, handle };
    window.scan = scan;
    void handle.outcome.then((outcome) => (scan.outcome = outcome));
  });
});
