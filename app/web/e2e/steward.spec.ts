/**
 * Asking a data steward from a project's page, by keyboard alone (docs/ui/steward-escalation-flows.md,
 * flow A): the shell's API answered from the fixtures app/tests/test_steward_escalations.py keeps
 * current. Nothing is sent until the researcher confirms in the dialog.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import escalations from "../fixtures/escalations.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import stewarding from "../fixtures/stewarding.json" with { type: "json" };
import { serveSession } from "./support";

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
});

for (const width of [1280, 320]) {
  test(`a researcher asks a data steward with the keyboard alone, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const sent: unknown[] = [];
    const base = `/api/projects/${project.project_id}`;
    await page.route(`${base}/documents`, (route) => route.fulfill({ json: project }));
    await page.route(`${base}/stewarding`, (route) => route.fulfill({ json: stewarding }));
    await page.route(`${base}/escalations`, (route) => {
      if (route.request().method() !== "POST") {
        return route.fulfill({ json: { ...escalations, escalations: [] } });
      }
      sent.push(route.request().postDataJSON());
      return route.fulfill({ status: 201, json: escalations });
    });
    await page.goto(`/projects/${project.project_id}`);

    const ask = page.getByRole("button", { name: "Ask a data steward" });
    await expect(ask).toBeEnabled();
    await ask.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Ask a data steward" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("group", { name: "What will be shared" })).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(sent).toEqual([]);

    await dialog.getByRole("textbox").focus();
    await page.keyboard.type("Can I share the recordings?");
    await dialog.getByRole("button", { name: "Send to a data steward" }).focus();
    await page.keyboard.press("Enter");

    await expect(dialog).toBeHidden();
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ note: "Can I share the recordings?", origin: { kind: "researcher" } });
    await expect(ask).toBeFocused();
    const scrolled = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(scrolled).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/steward-${width}.png`, fullPage: false });
  });
}
