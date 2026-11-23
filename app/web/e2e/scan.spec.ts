/**
 * Describe a folder… in the built shell, with the real browser scanner (#554), in Chromium: a folder whose files hold a canary string is described in the browser, its inventory
 * checked and added to the project from Make an inventory in its panel; and the same folder
 * described again under Edit inventory, as a new scan of the project's inventory, which is then
 * saved. The canary must be in no request the page makes, so in no body the app's API is sent.
 * The scanner's worker must be sent its own Content Security Policy.
 *
 * Needs the scanner's bundle: `npm ci && npm run bundle` in inventory/browser, which the preview
 * server then serves at /inventory-bundle/ (vite.config.ts). Chromium's own directory picker
 * cannot be driven by a test, so it is hidden and the folder is chosen with the
 * `<input webkitdirectory>` the dialog falls back to; the picker's route is unit tested
 * (DescribeFolder.test.tsx). The scanner itself is run in Firefox and WebKit by inventory/browser's
 * own browser tests, which take a folder the same way.
 */

import { cpSync, existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Page, type Request, expect, test } from "@playwright/test";

import { axeViolations, serveConversation, serveSession } from "./support";
import intake from "../fixtures/intake-complete.json" with { type: "json" };
import projects from "../fixtures/projects.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };

const CANARY = "dd-canary-5b1e04d2-do-not-send";
const SAMPLE = fileURLToPath(new URL("../../../inventory/tests/data/mixed", import.meta.url));
const BUNDLE = fileURLToPath(
  new URL("../../../inventory/browser/dist/inventory-bundle/manifest.json", import.meta.url),
);
const WORKER_POLICY = "default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'";

let root: string;
let folder: string;

test.beforeAll(() => {
  if (!existsSync(BUNDLE))
    throw new Error(
      "Build the scanner's bundle first: npm ci && npm run bundle in inventory/browser",
    );
  root = mkdtempSync(join(tmpdir(), "dd-app-scan-"));
  folder = join(root, "survey");
  cpSync(SAMPLE, folder, { recursive: true });
  writeFileSync(join(folder, "tables", "canary.csv"), `site,note\n1,${CANARY}\n`);
});

test.afterAll(() => rmSync(root, { recursive: true, force: true }));

/** Each request the page made was same-origin, and only the API's held more than a bodiless GET. */
function expectNoCanary(requests: Request[], baseURL: string | undefined) {
  const origin = new URL(baseURL ?? "").origin;
  for (const request of requests) {
    const url = new URL(request.url());
    expect(request.url()).not.toContain(CANARY);
    expect(request.postData() ?? "").not.toContain(CANARY);
    if (url.protocol === "blob:" || url.protocol === "data:") continue;
    expect(url.origin, request.url()).toBe(origin);
    if (!url.pathname.startsWith("/api/")) {
      expect(request.method(), request.url()).toBe("GET");
      expect(request.postData(), request.url()).toBeNull();
    }
  }
}

/** Offer the folder input browsers without a picker use, as Chromium's cannot be driven (above). */
async function withoutDirectoryPicker(page: Page) {
  await page.addInitScript(() => {
    delete (Window.prototype as { showDirectoryPicker?: unknown }).showDirectoryPicker;
    delete (window as { showDirectoryPicker?: unknown }).showDirectoryPicker;
  });
}

/**
 * Serve a workspace whose active project holds an inventory, so that its Project panel offers
 * Edit inventory and Replace the inventory; every inventory saved to it is recorded in `saved`.
 */
async function serveProjectPanel(page: Page) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await serveSession(page, development);
  await serveConversation(page);
  const [active] = projects;
  if (!active?.inventory) throw new Error("the projects fixture's first project holds no inventory");
  await page.route("/api/projects", (route) => route.fulfill({ json: projects }));
  await page.route(`/api/projects/${active.project_id}/progress`, (route) =>
    route.fulfill({ json: intake.progress }),
  );
  await page.route(`/api/projects/${active.project_id}/intake`, (route) => route.fulfill({ json: intake }));
  await page.addInitScript((id) => localStorage.setItem("dd-project", id), active.project_id);
  const stored = {
    schema_class: "FileInventory",
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0",
    inventory_made_at: active.inventory.inventory_made_at,
    inventory_files: [
      {
        file_path: "tables/plots.csv",
        file_size: 1,
        file_sha256: "0".repeat(64),
        file_media_type: "text/csv",
        file_pronom_ids: ["x-fmt/18"],
        file_identified_by: "extension",
        file_description: "The survey's main table",
      },
    ],
  };
  const saved: string[] = [];
  await page.route(`/api/projects/${active.project_id}/inventory`, async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: stored });
    saved.push(route.request().postData() ?? "");
    return route.fulfill({ status: 201, json: { ...active.inventory, revises: active.inventory?.digest } });
  });
  return { saved };
}

test("a folder is described in the browser and none of its content leaves it", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(150_000);
  const requests: Request[] = [];
  page.context().on("request", (request) => requests.push(request));
  await withoutDirectoryPicker(page);
  const { saved } = await serveProjectPanel(page);

  await page.goto("/");
  // The message box does not offer it; the project's panel does.
  await expect(page.getByRole("textbox", { name: "What would you like to do?" })).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Make an inventory" })).toHaveCount(0);
  await page.getByRole("region", { name: "Project" }).getByRole("button", { name: "Make an inventory" }).click();
  const dialog = page.getByRole("dialog", { name: "Make an inventory" });
  const describe = dialog.getByRole("region", { name: "Describe a folder in this browser" });
  await expect(describe.getByText(/None of the files is sent anywhere/)).toBeVisible();
  const worker = page.waitForResponse(/\/assets\/inventory-scanner-[^/]*\.js$/);
  await describe.locator('input[type="file"]').setInputFiles(folder);

  await expect(describe.getByRole("progressbar")).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
  expect((await worker).headers()["content-security-policy"]).toBe(WORKER_POLICY);

  const review = page.getByRole("dialog", { name: "Check the inventory" });
  await expect(review).toBeVisible({ timeout: 120_000 });
  await expect(review.getByText("canary.csv").first()).toBeVisible();
  await review.getByRole("button", { name: "Add this inventory" }).click();
  await expect.poll(() => saved.length).toBe(1);

  // The inventory was stored: the canary file by its path, made by the command under Pyodide.
  const [body] = saved;
  expect(body).toContain("tables/canary.csv");
  expect(body).toMatch(/"inventory_tool_version":"[^"]+\+pyodide\./);
  expectNoCanary(requests, baseURL);
});

test("a project's inventory is updated with a folder described in the browser", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(150_000);
  const requests: Request[] = [];
  page.context().on("request", (request) => requests.push(request));
  await withoutDirectoryPicker(page);
  const { saved } = await serveProjectPanel(page);

  await page.goto("/");
  await page.getByRole("region", { name: "Project" }).getByRole("button", { name: "Edit inventory" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit the project's inventory" });
  const describe = dialog.getByRole("region", { name: "Describe a folder in this browser" });
  await describe.locator('input[type="file"]').setInputFiles(folder);
  await expect(describe.getByRole("progressbar")).toBeVisible();

  await expect(dialog.getByRole("region", { name: "What the new scan changed" })).toBeVisible({
    timeout: 120_000,
  });
  await dialog.getByRole("button", { name: "Save as the project's inventory" }).click();
  await expect.poll(() => saved.length).toBe(1);
  const [body] = saved;
  expect(body).toContain("tables/canary.csv");
  expect(body).toMatch(/"inventory_tool_version":"[^"]+\+pyodide\./);
  expect(body).toContain("The survey's main table");
  expectNoCanary(requests, baseURL);
});
