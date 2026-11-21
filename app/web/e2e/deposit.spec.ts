/**
 * Building a project's deposit package, on its page (docs/specs/deposit.md): the shell's API
 * answered from the fixtures app/tests/test_deposit_package.py keeps current.
 *
 * A project with many files to decide has a long page, and building it removes the decisions and
 * the button pressed. The built package must still be where the person is looking (#1315).
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import built from "../fixtures/project-package.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import deposits from "../fixtures/project-deposits-none.json" with { type: "json" };
import reviewed from "../fixtures/project-review.json" with { type: "json" };
import repository from "../fixtures/repository-chosen.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { serveSession } from "./support";

const ID = project.project_id;
const DECIDED = {
  ...reviewed.items[0],
  decision: {
    decision: "keep",
    note: null,
    decided_at: built.review.confirmation.confirmed_at,
    decided_by: built.review.confirmation.confirmed_by,
  },
};
// The validation alone, as `POST /validation` answers, with as many files decided as a
// simulation dataset's inventory marks.
const READY = {
  ...Object.fromEntries(Object.entries(built).filter(([key]) => key !== "package")),
  review: {
    ...built.review,
    items: Array.from({ length: 90 }, (_, i) => ({
      ...DECIDED,
      item_id: String(i).padStart(24, "0"),
      path: `runs/run_${i}/output.h5`,
    })),
  },
};

function inView(box: { y: number; height: number } | null, height: number): boolean {
  return box !== null && box.y >= 0 && box.y + box.height <= height;
}

for (const width of [1280, 320]) {
  test(`the built package takes focus and is in view, at ${width}px`, async ({ page }) => {
    const height = 800;
    await page.setViewportSize({ width, height });
    await serveSession(page, development);
    const builds: string[] = [];
    await page.route(`/api/projects/${ID}/repository`, (route) =>
      route.fulfill({ json: repository }),
    );
    await page.route(`/api/projects/${ID}/deposits`, (route) => route.fulfill({ json: deposits }));
    await page.route(`/api/projects/${ID}/validation`, (route) =>
      route.fulfill({ status: 201, json: READY }),
    );
    await page.route(`/api/projects/${ID}/package`, (route) => {
      builds.push(route.request().method());
      return route.fulfill({ status: 201, json: { ...READY, package: built.package } });
    });
    await page.goto(`/projects/${ID}/deposit`);

    const panel = page.getByRole("region", { name: "Deposit package" });
    await panel.getByRole("button", { name: "Check the project" }).click();
    const build = panel.getByRole("button", { name: "Build the package" });
    await build.focus();
    await page.keyboard.press("Enter");

    const heading = panel.getByRole("heading", { name: "The package is built" });
    await expect(heading).toBeFocused();
    const download = panel.getByRole("link", { name: /Download the package/ });
    expect(inView(await download.boundingBox(), height)).toBe(true);
    expect(builds).toEqual(["POST"]);
    // The panel only: React Aria's own announcer, outside it, keeps the pending button's
    // announcement, which names the button the build removed.
    const scanned = await new AxeBuilder({ page }).include(".deposit").analyze();
    expect(scanned.violations).toEqual([]);
    await page.screenshot({ path: `test-results/deposit-${width}.png` });
  });
}
