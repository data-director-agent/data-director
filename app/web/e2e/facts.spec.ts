/**
 * Deciding what check agents proposed about a project, on its page (docs/specs/app.md, rule 29):
 * the shell's API answered from the fixtures app/tests/test_project_facts.py keeps current. A
 * proposal may be talked through first, in a new conversation, but is still decided only here.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import decided from "../fixtures/project-facts-decided.json" with { type: "json" };
import offered from "../fixtures/project-facts.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import projects from "../fixtures/projects.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { axeViolations, overflow, serveConversation, serveSession } from "./support";

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

for (const width of [1280, 320]) {
  test(`a link to a proposal lands on it, marked and focused, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.route(`/api/projects/${project.project_id}/documents`, (route) =>
      route.fulfill({ json: project }),
    );
    await page.route(`/api/projects/${project.project_id}/facts`, (route) =>
      route.fulfill({ json: offered }),
    );
    const sites = offered.proposals[1]?.fact;
    if (!sites) throw new Error("the fixture has no second proposal");
    const fact = new URLSearchParams({ fact: `${sites.fact_kind}:${sites.fact_subject}` });
    await page.goto(`/projects/${project.project_id}/facts?${fact.toString()}`);

    const card = page.getByRole("article", { name: /calibration\/sites\.csv/ });
    await expect(card).toBeFocused();
    await expect(card).toBeInViewport();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    const scrolled = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(scrolled).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/facts-linked-${width}.png`, fullPage: false });
  });
}

for (const width of [1280, 320]) {
  test(`a proposal is discussed in a new conversation, its question unsent, at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await serveConversation(page);
    const listed = [{ ...projects[0], project_id: project.project_id }];
    await page.route("/api/projects", (route) => route.fulfill({ json: listed }));
    await page.route(`/api/projects/${project.project_id}/**`, (route) =>
      route.request().url().endsWith("/facts")
        ? route.fulfill({ json: offered })
        : route.request().url().endsWith("/documents")
          ? route.fulfill({ json: project })
          : route.fallback(),
    );
    await page.addInitScript((id) => localStorage.setItem("dd-project", id), project.project_id);
    let sent = false;
    await page.route("/api/conversations/*/turns/stream", (route) => {
      sent = true;
      return route.abort();
    });
    await page.goto(`/projects/${project.project_id}/facts`);

    const duplicate = page.getByRole("article", { name: /readings \(copy\)\.csv/ });
    await duplicate.getByRole("link", { name: /Discuss this with Data Director/ }).press("Enter");

    const box = page.getByRole("textbox", { name: "What would you like to do?" });
    await expect(box).toBeFocused();
    await expect(box).toHaveValue(/readings \(copy\)\.csv/);
    await expect(box).toHaveValue(new RegExp(offered.proposals[0]?.agent_id ?? "unreachable"));
    await expect(page).toHaveURL(/\/$/);
    expect(sent).toBe(false);
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
}
