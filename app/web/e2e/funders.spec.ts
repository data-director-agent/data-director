/**
 * A funder's page, reached from Project Facts (docs/specs/app.md, rule 29): the fact and the
 * organisation behind its ROR identifier, the shell's API answered from the fixture
 * app/tests/test_funders.py keeps current.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import organisation from "../fixtures/funder-ror-organisation.json" with { type: "json" };
import offered from "../fixtures/project-facts.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { serveSession } from "./support";

const SUBJECT = "UKRI";
const funder = {
  fact_kind: "funder",
  fact_subject: SUBJECT,
  fact_funder_name: "UK Research and Innovation",
  fact_funder_ror: "001aqnf71",
};
const facts = { ...offered, decisions: [funder] };

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
  await page.route(`/api/projects/${project.project_id}/documents`, (route) =>
    route.fulfill({ json: project }),
  );
  await page.route(`/api/projects/${project.project_id}/facts`, (route) =>
    route.fulfill({ json: facts }),
  );
});

for (const width of [1280, 320]) {
  test(`a funder fact opens its page, and Back returns, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const asked: string[] = [];
    await page.route("/api/funders/ror/**", (route) => {
      asked.push(new URL(route.request().url()).pathname);
      return route.fulfill({ json: organisation });
    });
    await page.goto(`/projects/${project.project_id}/facts`);

    await page.getByRole("link", { name: /View funder/ }).click();

    await expect(page).toHaveURL(new RegExp(`funder=${SUBJECT}$`));
    await expect(page.getByRole("heading", { name: "UK Research and Innovation", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: organisation.ror_id })).toBeVisible();
    expect(asked).toEqual(["/api/funders/ror/001aqnf71"]);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    const scrolled = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(scrolled).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/funder-${width}.png`, fullPage: true });

    await page.getByRole("link", { name: /Back to the project's facts/ }).click();
    await expect(page.getByRole("heading", { name: "Decided" })).toBeVisible();
  });
}

test("a funder the dump does not hold is said so, without failing the page", async ({ page }) => {
  await page.route("/api/funders/ror/**", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      json: { type: "about:blank#organisation-not-found", title: "No such organisation", status: 404 },
    }),
  );
  await page.goto(`/projects/${project.project_id}/facts?funder=${SUBJECT}`);
  await expect(page.getByRole("alert")).toContainText("holds no organisation");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
