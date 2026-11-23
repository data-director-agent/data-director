/**
 * The browser scanner, as the app offers it (docs/specs/app.md, Make an inventory). The scanner
 * is `@data-director/inventory`'s: `dd-inventory` under Pyodide in a Web Worker with no network.
 * The app fetches the scanner's bundle from its own origin, at `inventory-bundle/`, and hands it
 * to a fresh worker for each scan, so that no byte of a chosen file is ever sent anywhere.
 *
 * A deployment offers the scanner by serving the bundle there (`npm run bundle` in
 * inventory/browser builds it). Where it does not, `available()` is false and the dialog offers
 * the command alone.
 */

import {
  fetchBundle,
  startScan,
  type BundleAssets,
  type ChosenFolder,
  type ScanEvent,
  type ScanHandle,
  type ScanOutcome,
  type WorkerLike,
} from "@data-director/inventory";
import ScanWorker from "@data-director/inventory/scanner/worker?worker";

/** Where the app serves the bundle, relative to the page. */
export const BUNDLE_PATH = "inventory-bundle/";
/** The bundle's licence notices (inventory/browser, `bundle/notices.ts`). */
export const NOTICES_PATH = `${BUNDLE_PATH}NOTICES.md`;

type Fetch = (url: string) => Promise<Response>;

export interface Scanner {
  /** Whether this deployment serves the scanner. A yes is kept; a no is asked again next time. */
  available(): Promise<boolean>;
  /** Describe `folder`. The bundle is fetched on the first scan and kept for the rest. */
  scan(folder: ChosenFolder, onEvent: (event: ScanEvent) => void): ScanHandle;
}

export interface ScannerOptions {
  /** The bundle's folder, ending in `/`; by default `inventory-bundle/` beside the page. */
  base?: string;
  fetcher?: Fetch;
  makeWorker?: () => WorkerLike;
}

async function servesBundle(base: string, fetcher: Fetch): Promise<boolean> {
  try {
    const response = await fetcher(`${base}manifest.json`);
    if (!response.ok) return false;
    const manifest = (await response.json()) as { entry?: unknown; files?: unknown };
    return typeof manifest.entry === "string" && typeof manifest.files === "object";
  } catch {
    return false;
  }
}

export function makeScanner({
  base = new URL(BUNDLE_PATH, document.baseURI).href,
  fetcher = (url) => fetch(url),
  makeWorker = () => new ScanWorker(),
}: ScannerOptions = {}): Scanner {
  let available: Promise<boolean> | undefined;
  let bundle: Promise<BundleAssets> | undefined;
  const loadBundle = (): Promise<BundleAssets> => {
    bundle ??= fetchBundle(base, fetcher).catch((error: unknown) => {
      bundle = undefined; // the next scan tries again
      throw error;
    });
    return bundle;
  };
  return {
    // Only a yes is kept: a failed fetch may be a hiccup, and keeping it would hide the browser
    // route until the page was reloaded. A no is asked again the next time the dialog opens.
    available() {
      if (available) return available;
      const asked = servesBundle(base, fetcher).then((yes) => {
        if (!yes && available === asked) available = undefined;
        return yes;
      });
      available = asked;
      return asked;
    },
    scan(folder, onEvent) {
      let handle: ScanHandle | undefined;
      let stopped = false;
      let stop!: () => void;
      const cancelled = new Promise<ScanOutcome>((resolve) => {
        stop = () => resolve({ status: "cancelled" });
      });
      const run = loadBundle().then(
        (assets): Promise<ScanOutcome> => {
          // Cancelled while the bundle was fetched: no worker is started.
          if (stopped) return Promise.resolve({ status: "cancelled" });
          handle = startScan(makeWorker(), assets, folder, onEvent);
          return handle.outcome;
        },
        (error: unknown): ScanOutcome => ({
          status: "failed",
          reason: error instanceof Error ? error.message : "The scanner could not be fetched.",
        }),
      );
      return {
        outcome: Promise.race([run, cancelled]),
        cancel() {
          stopped = true;
          stop();
          handle?.cancel();
        },
      };
    },
  };
}

let shared: Scanner | undefined;

/** The page's scanner, made when first asked for. */
export function pageScanner(): Scanner {
  shared ??= makeScanner();
  return shared;
}

/** Put `scanner` in place of the page's, as the unit tests do with one that is not served. */
export function setPageScanner(scanner: Scanner): void {
  shared = scanner;
}
