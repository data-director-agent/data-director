/**
 * Nothing moves under the pointer as what a page reads arrives (#1328): with the server's answers
 * landing one after another, as at a workshop with many people working at once, the page shifts
 * no more than `MAX_LAYOUT_SHIFT`, and the buttons a researcher presses next stay where they were
 * first drawn. Measured with the Layout Instability API, so in Chromium only.
 */

import { type Locator, type Page, expect, test } from "@playwright/test";

import pending from "../fixtures/intake-pending.json" with { type: "json" };
import documents from "../fixtures/project-documents.json" with { type: "json" };
import projects from "../fixtures/projects.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import {
  MAX_LAYOUT_SHIFT,
  layoutShift,
  serveConversation,
  serveLate,
  serveSession,
  watchShifts,
} from "./support";

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
});

const [first] = projects;
if (!first) throw new Error("the projects fixture lists no project");
const active = first;
const project = `/api/projects/${active.project_id}`;

/** Where `part` is on the page, not in the viewport, so that scrolling moves nothing. */
async function placed(page: Page, part: Locator) {
  const box = await part.boundingBox();
  const scrollY = await page.evaluate(() => window.scrollY);
  return box && { ...box, y: box.y + scrollY };
}

/** The active project's reads, each answered later than the one before. */
async function serveProjectLate(page: Page) {
  await serveLate(page, "/api/projects", 200, projects);
  await serveLate(page, `${project}/progress`, 400, pending.progress);
  await serveLate(page, `${project}/intake`, 600, pending);
  await serveLate(page, `${project}/documents`, 800, documents);
  await page.addInitScript((id) => localStorage.setItem("dd-project", id), active.project_id);
}

for (const width of [1280, 320]) {
  test(`at ${width}px the workspace does not move as the project loads`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await watchShifts(page);
    await serveConversation(page);
    await serveProjectLate(page);
    await page.goto("/");

    const next = page.getByRole("button", { name: "Next", exact: true });
    const attach = page.getByRole("button", { name: "Attach a file" });
    await expect(next).toBeVisible();
    const drawn = [await placed(page, next), await placed(page, attach)];
    await page.waitForLoadState("networkidle");

    expect([await placed(page, next), await placed(page, attach)]).toEqual(drawn);
    expect(await layoutShift(page)).toBeLessThanOrEqual(MAX_LAYOUT_SHIFT);
  });

  test(`at ${width}px the document check moves no button as it answers`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await watchShifts(page);
    await serveConversation(page);
    await serveLate(page, "/api/documentation/check", 600, {
      findings: [{ kind: "email address", places: "1", confidence: "high" }],
      kinds: ["email address"],
      checked_with: "patterns",
    });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Attach a file" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await layoutShift(page, true);

    await page.locator('input[type="file"]').setInputFiles({
      name: "protocol.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Protocol\n\nWrite to the team at the address on the website.\n"),
    });
    const review = page.getByRole("dialog", { name: "Check the document before attaching it" });
    const attach = review.getByRole("button", { name: /^Attach/ });
    await expect(attach).toBeDisabled();
    // The dialog is fixed to the window, so its buttons are placed in the viewport.
    const drawn = await attach.boundingBox();

    await expect(review.getByRole("checkbox")).toBeVisible();
    const after = await attach.boundingBox();
    expect(after && { y: after.y, bottom: after.y + after.height }).toEqual(
      drawn && { y: drawn.y, bottom: drawn.y + drawn.height },
    );
    expect(await layoutShift(page)).toBeLessThanOrEqual(MAX_LAYOUT_SHIFT);
  });

  test(`at ${width}px the project page does not move as it loads`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await watchShifts(page);
    await serveConversation(page);
    await serveLate(page, `${project}/documents`, 200, documents);
    await serveLate(page, "/api/projects", 600, projects);
    await page.goto(`/projects/${active.project_id}`);

    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await layoutShift(page)).toBeLessThanOrEqual(MAX_LAYOUT_SHIFT);
  });
}
