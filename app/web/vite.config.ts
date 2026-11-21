import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync } from "node:fs";
import { join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { searchForWorkspaceRoot, type Connect } from "vite";
import { defineConfig } from "vitest/config";

// @data-director/inventory and @data-director/agent-view are linked from inventory/browser and
// sdk/browser and served as source, so the dev server may read them as well as this folder.
const INVENTORY = fileURLToPath(new URL("../../inventory/browser", import.meta.url));
const AGENT_VIEW = fileURLToPath(new URL("../../sdk/browser", import.meta.url));

// The app's Python server (`uv run data-director`) serves /api; `npm run dev` proxies to it.
const API = process.env.DD_APP_URL ?? "http://127.0.0.1:7860";
// The model broker's enrolment interface, at /broker/enrolment on the page's own origin as nginx
// serves it (docs/specs/model-accounts.md, Enrolment). Only that path is passed on.
const BROKER = process.env.DD_BROKER_URL ?? "http://127.0.0.1:8300";
// The deposit broker's account interface, at /deposit-broker/connect likewise (docs/specs/deposit.md).
const DEPOSIT_BROKER = process.env.DD_DEPOSIT_BROKER_URL ?? "http://127.0.0.1:8310";

// The browser scanner (`@data-director/inventory`, README.md, Browser scanner). Its bundle is built
// apart (`npm run bundle` in inventory/browser) and served, when built, at /inventory-bundle/ by
// the dev and preview servers; `vite build` leaves it out of dist. The built worker is sent the
// policy it runs under in production (dd_app.worker_policy), so the end-to-end test runs under it
// too. The dev server serves the worker as separate modules from this origin, which that policy
// would refuse, so there it runs without one.
const BUNDLE = fileURLToPath(
  new URL("../../inventory/browser/dist/inventory-bundle", import.meta.url),
);
const BUNDLE_PATH = "/inventory-bundle/";
const WORKER = /^\/assets\/inventory-scanner-[^/]*\.js$/;
const WORKER_POLICY = "default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'";

function serveScanner(withPolicy: boolean): Connect.NextHandleFunction {
  return (request, response, next) => {
    const path = new URL(request.url ?? "/", "http://localhost").pathname;
    if (withPolicy && WORKER.test(path))
      response.setHeader("Content-Security-Policy", WORKER_POLICY);
    if (!path.startsWith(BUNDLE_PATH)) return next();
    const file = join(BUNDLE, normalize(decodeURIComponent(path.slice(BUNDLE_PATH.length))));
    if (!file.startsWith(BUNDLE + "/") || !existsSync(file) || !statSync(file).isFile()) {
      response.statusCode = 404;
      return response.end();
    }
    response.setHeader("Content-Length", statSync(file).size);
    createReadStream(file).pipe(response);
  };
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "inventory-scanner",
      configureServer: (server) => void server.middlewares.use(serveScanner(false)),
      configurePreviewServer: (server) => void server.middlewares.use(serveScanner(true)),
    },
  ],
  worker: {
    format: "es",
    rolldownOptions: {
      output: { entryFileNames: "assets/inventory-scanner-[hash].js" },
    },
  },
  // agent-view's components import React from its own folder, where its tests install a copy; one
  // React for the whole page, the app's.
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    proxy: {
      "/api": API,
      "/broker/enrolment/": {
        target: BROKER,
        rewrite: (path: string) => path.replace(/^\/broker/, ""),
      },
      "/deposit-broker/connect/": {
        target: DEPOSIT_BROKER,
        rewrite: (path: string) => path.replace(/^\/deposit-broker/, ""),
      },
    },
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), INVENTORY, AGENT_VIEW] },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    // In one chunk the bundle passed Vite's 500 kB warning (#212). Lazy loading would not
    // help: React, React Aria and the Markdown renderer are all needed by the first page. So
    // the vendors go in their own chunks instead, each well under the limit, which a browser
    // keeps cached across releases that change only the app's own code. The first group a
    // module matches wins, so `vendor` collects whatever the two before it leave.
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            {
              name: "react-aria",
              test: /node_modules[\\/](react-aria|react-stately|@react-aria|@react-stately|@react-types|@internationalized|@swc)/,
            },
            { name: "vendor", test: /node_modules[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // A test that drives a whole run and then checks it with axe takes about three seconds, and
    // coverage instrumentation adds two thirds again, which is past Vitest's default of five.
    testTimeout: 15_000,
    // Test files share a worker's module cache rather than each loading jsdom, React and the
    // components afresh: about half the run time. Testing Library's cleanup after each test
    // (src/test/setup.ts) clears the DOM; a test that changes module state must restore it.
    isolate: false,
    // Measured only with --coverage, as CI runs it, so that `npm test` stays quick. The text
    // file is the job summary (fully covered files left out, as the Python report does); lcov
    // goes to Codecov under the `web` flag (codecov.yml), its paths from the repository root.
    // The floors sit a few points under the measured figures (87, 76, 89 and 90% when set), so
    // ordinary variation does not fail a run; Codecov holds the figures from falling.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      reporter: [
        "text",
        ["text", { file: "coverage.txt", skipFull: true }],
        ["lcov", { projectRoot: "../.." }],
      ],
      thresholds: { statements: 82, branches: 71, functions: 84, lines: 85 },
    },
  },
});
