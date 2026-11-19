import { createReadStream, existsSync, statSync } from "node:fs";
import { join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

/**
 * Builds the test page (`page/`) into `dist/e2e-page/` and previews it with the bundle
 * (`dist/inventory-bundle/`, at `/inventory-bundle/`) from one origin, as the app is to. The
 * worker is sent the policy it is meant to run under: no network, and scripts only from the
 * `blob:` URLs it makes of the bundle's bytes.
 */
export const WORKER_POLICY =
  "default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'";
const PAGE_POLICY =
  "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; style-src 'self'";

const BUNDLE = fileURLToPath(new URL("../dist/inventory-bundle", import.meta.url));
const BUNDLE_PATH = "/inventory-bundle/";

function scannerServer(): Plugin {
  return {
    name: "scanner-server",
    configurePreviewServer(server) {
      server.middlewares.use((request, response, next) => {
        const url = new URL(request.url ?? "/", "http://localhost").pathname;
        const worker = /\/assets\/worker-[^/]*\.js$/.test(url);
        response.setHeader("Content-Security-Policy", worker ? WORKER_POLICY : PAGE_POLICY);
        if (!url.startsWith(BUNDLE_PATH)) return next();
        const file = join(BUNDLE, normalize(decodeURIComponent(url.slice(BUNDLE_PATH.length))));
        if (!file.startsWith(BUNDLE) || !existsSync(file) || !statSync(file).isFile()) {
          response.statusCode = 404;
          return response.end();
        }
        response.setHeader("Content-Length", statSync(file).size);
        createReadStream(file).pipe(response);
      });
    },
  };
}

export default defineConfig({
  root: fileURLToPath(new URL("page", import.meta.url)),
  publicDir: false,
  build: {
    outDir: fileURLToPath(new URL("../dist/e2e-page", import.meta.url)),
    emptyOutDir: true,
  },
  worker: { format: "es" },
  plugins: [scannerServer()],
});
