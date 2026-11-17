/**
 * What the page and the scanner's worker say to each other, and `startScan`, the page's side.
 * The page hands the worker the bundle and the chosen folder; the worker answers with stages,
 * progress, and the inventory or why there is none. Cancelling ends the worker
 * (`worker.terminate()`): a scan cannot be paused or resumed.
 */

import type { BundleAssets } from "./assets";
import type { ChosenFolder } from "./choose";
import type { FileProgress } from "./runtime";

/** Page to worker: describe this folder with this bundle. */
export interface ScanRequest {
  type: "scan";
  assets: BundleAssets;
  folder: ChosenFolder;
}

/** What the worker is doing before the first file: starting Python, installing, mounting. */
export type ScanStage = "starting" | "installing" | "reading";

/** Worker to page. */
export type ScanEvent =
  | { type: "stage"; stage: ScanStage }
  | ({ type: "progress" } & FileProgress)
  | { type: "done"; inventory: string }
  | { type: "failed"; reason: string };

/** How a scan ended: the inventory's JSON text, why there is none, or that it was cancelled. */
export type ScanOutcome =
  | { status: "done"; inventory: string }
  | { status: "failed"; reason: string }
  | { status: "cancelled" };

/** A `Worker`, as far as the page uses one. */
export type WorkerLike = Pick<Worker, "postMessage" | "terminate" | "onmessage" | "onerror">;

/** A scan under way: its outcome, once it ends, and a way to end it now. */
export interface ScanHandle {
  outcome: Promise<ScanOutcome>;
  cancel(): void;
}

/**
 * Start a scan in `worker`, which must be fresh: it is ended with the scan, whatever the outcome.
 * `onEvent` hears every stage and file as they happen.
 */
export function startScan(
  worker: WorkerLike,
  assets: BundleAssets,
  folder: ChosenFolder,
  onEvent: (event: ScanEvent) => void = () => undefined,
): ScanHandle {
  let finish: (outcome: ScanOutcome) => void = () => undefined;
  const outcome = new Promise<ScanOutcome>((resolve) => {
    finish = (result) => {
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
      resolve(result);
    };
  });
  worker.onmessage = ({ data }: MessageEvent<ScanEvent>) => {
    onEvent(data);
    if (data.type === "done") finish({ status: "done", inventory: data.inventory });
    else if (data.type === "failed") finish({ status: "failed", reason: data.reason });
  };
  worker.onerror = (event) =>
    finish({ status: "failed", reason: event.message || "The scanner stopped unexpectedly." });
  const request: ScanRequest = { type: "scan", assets, folder };
  worker.postMessage(request);
  return { outcome, cancel: () => finish({ status: "cancelled" }) };
}
