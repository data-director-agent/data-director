/**
 * A project's FAIR feedback tab (docs/ui/fair-feedback.md, #433): the counts for each principle,
 * what to do next and each stored report, readable at any width and with no accessibility
 * violation. The shell's API is answered from the fixture that
 * app/tests/test_project_runs_by_class.py keeps current, with an earlier report made from it that
 * met one check fewer.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import project from "../fixtures/project-documents.json" with { type: "json" };
import stored from "../fixtures/project-fairness-runs.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { overflow, serveSession } from "./support";

const [latest] = stored.runs;

/** The stored report as it was before its first met check was met. */
function earlier(): unknown {
  if (!latest) throw new Error("the fixture holds no run");
  const payload = structuredClone(latest.payload);
  const check = payload.checks.find((c) => c.met);
  if (!check) throw new Error("the fixture's report meets no check");
  check.met = false;
  const tally = payload.principle_tallies.find((t) => t.principle_group === check.principle.charAt(0));
  if (tally) tally.tally_met -= 1;
  return { ...latest, invocation_id: "earlier", completed_at: "2025-12-31T00:00:00Z", payload };
}

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
});

for (const width of [1280, 320]) {
  test(`the FAIR feedback tab shows each principle's count and each report, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route(`/api/projects/${project.project_id}/documents`, (route) => route.fulfill({ json: project }));
    await page.route(`/api/projects/${project.project_id}/runs?*`, (route) =>
      route.fulfill({ json: { runs: [latest, earlier()] } }),
    );
    await page.goto(`/projects/${project.project_id}/fair`);

    const panel = page.getByRole("region", { name: "FAIR feedback" });
    await expect(panel.getByRole("meter").first()).toBeVisible();
    await expect(panel.getByRole("region", { name: "What to do next" })).toBeVisible();
    await expect(panel.getByRole("table")).toBeVisible();
    await expect(panel).toContainText("Not a FAIRness evaluation");
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/fair-${width}.png`, fullPage: true });
  });
}
