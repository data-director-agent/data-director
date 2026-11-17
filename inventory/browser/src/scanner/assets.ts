/**
 * The browser bundle's files (README.md, Browser bundle), fetched by the page and handed to the
 * scanner's worker, which has no network of its own (`connect-src 'none'`). Inside the worker,
 * `serveFrom` answers Pyodide's requests for them from memory and refuses every other request.
 */

/** Where Pyodide is told the bundle is, inside the worker. Nothing is ever fetched from it. */
export const BUNDLE_URL = "https://inventory-bundle.invalid/";

/** The bundle's `manifest.json`, as far as the scanner reads it (`bundle/manifest.ts`). */
export interface BundleManifest {
  pyodide: string;
  /** The package whose installation installs the rest (`loadPackage(entry)`). */
  entry: string;
  /** Every file in the bundle, by its path in it. */
  files: Record<string, unknown>;
}

/** The bundle as the worker is handed it: its manifest, and every file's bytes by its path. */
export interface BundleAssets {
  manifest: BundleManifest;
  files: Record<string, ArrayBuffer>;
}

type Fetch = (url: string) => Promise<Response>;

/**
 * Fetch the whole bundle from `baseUrl` (ending in `/`), the folder the app serves it from on its
 * own origin. Throws when a file cannot be fetched: a configuration error, not a content problem.
 */
export async function fetchBundle(
  baseUrl: string,
  fetcher: Fetch = (url) => fetch(url),
): Promise<BundleAssets> {
  const get = async (path: string): Promise<Response> => {
    const response = await fetcher(baseUrl + path);
    if (!response.ok) throw new Error(`The scanner's ${path} could not be fetched.`);
    return response;
  };
  const manifest = (await (await get("manifest.json")).json()) as BundleManifest;
  const files = await Promise.all(
    Object.keys(manifest.files).map(async (path) => [path, await (await get(path)).arrayBuffer()]),
  );
  return { manifest, files: Object.fromEntries(files) as Record<string, ArrayBuffer> };
}

function base64(bytes: ArrayBuffer): string {
  let text = "";
  for (const byte of new Uint8Array(bytes)) text += String.fromCharCode(byte);
  return btoa(text);
}

/** Whether `bytes` match a subresource integrity value such as `sha256-…` (any one of several). */
export async function matchesIntegrity(bytes: ArrayBuffer, integrity: string): Promise<boolean> {
  const algorithms = { sha256: "SHA-256", sha384: "SHA-384", sha512: "SHA-512" } as const;
  for (const value of integrity.trim().split(/\s+/)) {
    const [name, digest] = value.split("-", 2) as [string, string | undefined];
    const algorithm = algorithms[name as keyof typeof algorithms];
    if (algorithm && digest && base64(await crypto.subtle.digest(algorithm, bytes)) === digest)
      return true;
  }
  return false;
}

function urlOf(input: string | URL | Request): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

/**
 * A `fetch` that answers from the bundle's bytes, for requests under `BUNDLE_URL`, and refuses
 * everything else. It honours the `integrity` Pyodide gives for each wheel, as the browser would.
 */
export function serveFrom(files: Record<string, ArrayBuffer>): typeof fetch {
  return async (input: string | URL | Request, init?: RequestInit) => {
    const url = urlOf(input);
    const path = url.startsWith(BUNDLE_URL) ? url.slice(BUNDLE_URL.length) : undefined;
    const bytes = path === undefined ? undefined : files[path];
    if (path === undefined || bytes === undefined)
      throw new TypeError(`The scanner fetches nothing beyond its bundle: ${url}`);
    if (init?.integrity && !(await matchesIntegrity(bytes, init.integrity)))
      throw new TypeError(`The scanner's ${path} does not match its digest.`);
    const type = path.endsWith(".wasm") ? "application/wasm" : "application/octet-stream";
    return new Response(bytes.slice(0), { headers: { "Content-Type": type } });
  };
}
