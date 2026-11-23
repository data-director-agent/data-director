/**
 * Asking a data steward from a project's page, by keyboard alone (docs/ui/steward-escalation-flows.md,
 * flow A), and a steward taking the request from their queue and opening the project as its
 * steward (flow C): the shell's API answered from the fixtures app/tests/test_steward_escalations.py
 * keeps current. Nothing is sent until the researcher confirms in the dialog.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import escalations from "../fixtures/escalations.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import stewarding from "../fixtures/stewarding.json" with { type: "json" };
import queue from "../fixtures/steward-queue.json" with { type: "json" };
import view from "../fixtures/project-steward-view.json" with { type: "json" };
import { axeViolations, overflow, serveSession } from "./support";

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

const steward = {
  ...development,
  principal: {
    ...development.principal,
    roles: ["researcher", "steward"],
    teams: [{ team_id: "library-rdm", name: "Library Research Data Team" }],
  },
};

for (const width of [1280, 320]) {
  test(`a steward takes a request and opens its project with the keyboard alone, at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await serveSession(page, steward);
    const [row] = queue.escalations;
    if (!row) throw new Error("no escalation in the fixture");
    const taken = { ...row, state: "taken", taken_by: development.principal, permitted_moves: [] };
    const moves: unknown[] = [];
    await page.route("/api/steward/escalations?*", (route) =>
      route.fulfill({ json: { escalations: [moves.length ? taken : row] } }),
    );
    await page.route(`/api/steward/escalations/${row.project_id}/${row.escalation_id}`, (route) => {
      moves.push(route.request().postDataJSON());
      return route.fulfill({ json: taken });
    });
    const base = `/api/projects/${row.project_id}`;
    await page.route(base, (route) => route.fulfill({ json: view }));
    await page.route(`${base}/documents`, (route) => route.fulfill({ json: project }));
    await page.route(`${base}/stewarding`, (route) => route.fulfill({ json: stewarding }));
    await page.route(`${base}/escalations`, (route) =>
      route.fulfill({ json: { ...escalations, escalations: [taken] } }),
    );

    await page.goto("/steward");
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Requests" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const take = page.getByRole("button", { name: /^Take/ });
    await take.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("cell", { name: development.principal.name })).toBeVisible();
    expect(moves).toEqual([{ move: "take" }]);
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);

    await page.getByRole("link", { name: row.project_title ?? "" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: /Viewing as a data steward/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ask a data steward" })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/steward-view-${width}.png`, fullPage: false });
  });
}
