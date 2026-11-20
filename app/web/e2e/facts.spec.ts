/**
 * Deciding what check agents proposed about a project, on its page (docs/specs/app.md, rule 29):
 * the shell's API answered from the fixtures app/tests/test_project_facts.py keeps current.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import decided from "../fixtures/project-facts-decided.json" with { type: "json" };
import offered from "../fixtures/project-facts.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { serveSession } from "./support";

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
});

for (const width of [1280, 320]) {
  test(`a proposal is confirmed with the keyboard alone, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const sent: unknown[] = [];
    await page.route(`/api/projects/${project.project_id}/documents`, (route) =>
      route.fulfill({ json: project }),
    );
    await page.route(`/api/projects/${project.project_id}/facts`, (route) =>
      route.fulfill({ json: offered }),
    );
    await page.route(`/api/projects/${project.project_id}/facts/decisions`, (route) => {
      sent.push(route.request().postDataJSON());
      return route.fulfill({ status: 201, json: decided });
    });
    await page.goto(`/projects/${project.project_id}/facts`);

    const panel = page.getByRole("region", { name: "Project facts" });
    const duplicate = panel.getByRole("article", { name: /readings \(copy\)\.csv/ });
    await expect(duplicate).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

    await duplicate.getByRole("button", { name: "Confirm" }).focus();
    await page.keyboard.press("Enter");

    await expect(panel.getByRole("status")).toContainText("Recorded:");
    expect(sent).toEqual([{ verdict: "confirmed", proposal: offered.proposals[0]?.proposal }]);
    const scrolled = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(scrolled).toBeLessThanOrEqual(0);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/facts-${width}.png`, fullPage: true });
  });
}
