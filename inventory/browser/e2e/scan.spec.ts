/**
 * The browser scanner in Chromium: the command, under Pyodide in a worker that has no network,
 * describes a folder chosen with `<input webkitdirectory>` as the command does natively, and no
 * file's content leaves the browser.
 */

import { expect, test, type Page, type Request } from "@playwright/test";
import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { parityProblems } from "../bundle/compare.ts";
import { nativeInventory, SAMPLE, type Inventory } from "../bundle/native.ts";
import type { ScanEvent, ScanOutcome } from "../src/index.ts";

/** A string in a file of the folder, which must appear in no request and not in the inventory. */
const CANARY = "dd-canary-7f3c9a1e-do-not-send";

let folder: string;

test.beforeAll(() => {
  folder = join(mkdtempSync(join(tmpdir(), "dd-scanner-")), "sample");
  cpSync(SAMPLE, folder, { recursive: true });
  writeFileSync(join(folder, "tables", "canary.csv"), `site,note\nA,${CANARY}\nB,${CANARY}\n`);
});

test.afterAll(() => rmSync(join(folder, ".."), { recursive: true, force: true }));

function recordRequests(page: Page): Request[] {
  const requests: Request[] = [];
  page.context().on("request", (request) => requests.push(request));
  return requests;
}

async function chooseFolder(page: Page): Promise<void> {
  await page.goto("/");
  await page.locator("#folder").setInputFiles(folder);
}

async function outcomeOf(page: Page): Promise<ScanOutcome> {
  const outcome = await page.waitForFunction(() => window.scan?.outcome, undefined, {
    timeout: 100_000,
  });
  return (await outcome.jsonValue()) as ScanOutcome;
}

test("describes a folder as the command does, and sends none of it", async ({ page }) => {
  const requests = recordRequests(page);
  await chooseFolder(page);
  const outcome = await outcomeOf(page);
  expect(outcome.status, JSON.stringify(outcome)).toBe("done");
  const inventory = JSON.parse((outcome as { inventory: string }).inventory) as Inventory;

  const native = nativeInventory(folder);
  const version = String(inventory.inventory_tool_version);
  const runtime = version.slice(version.indexOf("+") + 1);
  expect(runtime).toMatch(/^pyodide\./);
  expect(parityProblems(native, inventory, runtime)).toEqual([]);

  const events = await page.evaluate(() => window.scan?.events ?? []);
  const progress = events.filter(
    (e): e is Extract<ScanEvent, { type: "progress" }> => e.type === "progress",
  );
  const files = inventory.inventory_files as unknown[];
  expect(progress.at(-1)).toMatchObject({ done: files.length, total: files.length });

  expect(JSON.stringify(inventory)).not.toContain(CANARY);
  const origin = new URL(page.url()).origin;
  for (const request of requests) {
    expect(request.method(), request.url()).toBe("GET");
    expect(request.postDataBuffer(), request.url()).toBeNull();
    expect(new URL(request.url()).origin, request.url()).toBe(origin);
    expect(request.url()).not.toContain(CANARY);
  }
});

test("a cancelled scan ends its worker", async ({ page }) => {
  await chooseFolder(page);
  await page.waitForFunction(() => window.scan);
  await page.evaluate(() => window.scan?.handle.cancel());
  expect(await outcomeOf(page)).toEqual({ status: "cancelled" });
});
