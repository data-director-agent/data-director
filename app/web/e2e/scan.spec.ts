/**
 * Describe a folder… in the built shell, with the real browser scanner (#554), in Chromium, Firefox
 * and WebKit: a folder whose files hold a canary string is described in the browser, its inventory
 * checked and attached to a message, and the message sent. The canary must be in no request the
 * page makes, so in no body the app's API is sent. A turn's body is what the harness would store,
 * so no stored event can hold it either. The scanner's worker must be sent its own Content Security Policy.
 *
 * Needs the scanner's bundle: `npm ci && npm run bundle` in inventory/browser, which the preview
 * server then serves at /inventory-bundle/ (vite.config.ts). Chromium's own directory picker
 * cannot be driven by a test, so it is hidden and the folder is chosen with the
 * `<input webkitdirectory>` the dialog falls back to; the picker's route is unit tested
 * (DescribeFolder.test.tsx).
 */

import { cpSync, existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Request, expect, test } from "@playwright/test";

import { axeViolations, serveConversation, serveSession, turnSent } from "./support";
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

test("a folder is described in the browser and none of its content leaves it", async ({
  page,
  baseURL,
  browserName,
}) => {
  test.setTimeout(150_000);
  const requests: Request[] = [];
  page.context().on("request", (request) => requests.push(request));
  // The fallback a browser without the directory picker uses (see above).
  await page.addInitScript(() => {
    delete (Window.prototype as { showDirectoryPicker?: unknown }).showDirectoryPicker;
    delete (window as { showDirectoryPicker?: unknown }).showDirectoryPicker;
  });
  await serveSession(page, development);
  await serveConversation(page);
  const sent: string[] = [];
  await page.route("/api/conversations/*/turns/stream", async (route) => {
    sent.push(JSON.stringify(turnSent(route)));
    await route.fallback();
  });

  await page.goto("/");
  await page.getByRole("textbox", { name: "What would you like to do?" }).fill("Describe this");
  await page.getByRole("button", { name: "Make an inventory" }).click();
  const dialog = page.getByRole("dialog", { name: "Make an inventory" });
  const describe = dialog.getByRole("region", { name: "Describe a folder in this browser" });
  await expect(describe.getByText(/None of the files is sent anywhere/)).toBeVisible();
  const worker = page.waitForResponse(/\/assets\/inventory-scanner-[^/]*\.js$/);
  await describe.locator('input[type="file"]').setInputFiles(folder);

  await expect(describe.getByRole("progressbar")).toBeVisible();
  // In Playwright's Firefox, axe crashes the page once `getByRole("region")` has been queried, with
  // or without a scan running, so the dialog's accessibility is checked in Chromium and WebKit.
  if (browserName !== "firefox") expect(await axeViolations(page)).toEqual([]);
  expect((await worker).headers()["content-security-policy"]).toBe(WORKER_POLICY);

  const review = page.getByRole("dialog", { name: "Check the inventory before attaching it" });
  await expect(review).toBeVisible({ timeout: 120_000 });
  await expect(review.getByText("canary.csv").first()).toBeVisible();
  await review.getByRole("button", { name: "Attach this inventory" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(1);

  // The inventory was sent: the canary file by its path, made by the command under Pyodide.
  const [body] = sent;
  expect(body).toContain("tables/canary.csv");
  expect(body).toMatch(/"inventory_tool_version":"[^"]+\+pyodide\./);
  // Nothing the page asked for carried the canary, and nothing but the API was more than a
  // same-origin GET.
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
});
