/**
 * Reading a document a researcher attached, on the project's Documents tab (docs/specs/app.md):
 * listed after the drafts, opened laid out from the Markdown a Word document is read as, with the
 * original to download, and no conversations beside it. The shell's API is answered here.
 */

import { expect, test } from "@playwright/test";

import project from "../fixtures/project-documents.json" with { type: "json" };
import answers from "../fixtures/project-answers.json" with { type: "json" };
import drafted from "../fixtures/project-drafted.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import { axeViolations, overflow, serveSession } from "./support";

const DMP = {
  documentation_name: "dmp.docx",
  documentation_digest: "a".repeat(64),
  documentation_media_type: "text/markdown",
  documentation_size: 230,
  documentation_added_at: "2026-11-10T10:00:00Z",
  documentation_source_media_type:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};
const MARKDOWN = [
  "# Data management plan",
  "## Data collection",
  "Soil cores were taken weekly at 10 cm depth.",
  "- Soil moisture\n- Soil temperature",
  "| Output | Repository |\n| --- | --- |\n| Cores | Zenodo |",
].join("\n\n");

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
  const base = `/api/projects/${project.project_id}`;
  await page.route(`${base}/documents`, (route) => route.fulfill({ json: project }));
  await page.route(`${base}/documentation`, (route) => route.fulfill({ json: [DMP] }));
  await page.route(`${base}/documentation/${DMP.documentation_digest}*`, (route) =>
    route.fulfill({ body: MARKDOWN, contentType: "text/markdown; charset=utf-8" }),
  );
});

for (const width of [1280, 320]) {
  test(`an attached Word document is read laid out, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/projects/${project.project_id}?attached=${DMP.documentation_digest}`);

    const article = page.getByRole("article", { name: DMP.documentation_name });
    await expect(article.getByRole("heading", { name: "Data collection" })).toBeVisible();
    await expect(article.getByRole("table")).toBeVisible();
    await expect(article.getByRole("link", { name: /Download/ })).toHaveAttribute(
      "href",
      /\?original$/,
    );
    await expect(page.getByRole("navigation", { name: /Conversations/ })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/attached-${width}.png`, fullPage: true });

    if (width > 320) {
      const list = page.getByRole("navigation", { name: "Documents" });
      await expect(list.getByRole("link", { name: /dmp\.docx/ })).toHaveAttribute(
        "aria-current",
        "page",
      );
    }
  });
}

for (const width of [1280, 320]) {
  test(`a draft's open questions are a tab beside its text, counted, at ${width}px`, async ({
    page,
  }) => {
    const [document] = answers.documents;
    if (!document) throw new Error("The fixture holds no document.");
    const asking = { ...answers, documents: [{ ...document, answers: [] }] };
    await page.route(`/api/projects/${answers.project_id}/documents`, (route) =>
      route.fulfill({ json: asking }),
    );
    await page.route(`/api/projects/${answers.project_id}/documentation`, (route) =>
      route.fulfill({ json: [] }),
    );
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/projects/${answers.project_id}?doc=${document.document_id}`);

    const tab = page.getByRole("tab", { name: "Questions 1 open" });
    await expect(tab).toBeVisible();
    await page.screenshot({ path: `test-results/questions-count-${width}.png` });
    await tab.click();
    const panel = page.getByRole("tabpanel", { name: /^Questions/ });
    await expect(panel.getByText(/0 of 1 answered/)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/questions-tab-${width}.png` });
  });
}

for (const width of [1280, 320]) {
  test(`with every question answered, the next draft is asked for from the page, at ${width}px`, async ({
    page,
  }) => {
    const [document] = drafted.documents;
    const [first] = document?.versions ?? [];
    if (!document || !first) throw new Error("The fixture holds no draft.");
    const before = { ...drafted, documents: [{ ...document, versions: [first] }] };
    const base = `/api/projects/${drafted.project_id}`;
    let asked: unknown = null;
    await page.route(`${base}/documents`, (route) => route.fulfill({ json: before }));
    await page.route(`${base}/documentation`, (route) => route.fulfill({ json: [] }));
    await page.route(`${base}/documents/${document.document_id}/drafts`, (route) => {
      asked = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: drafted });
    });
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/projects/${drafted.project_id}?doc=${document.document_id}`);

    const drafting = page.getByRole("region", { name: "Continue drafting" });
    await expect(drafting.getByText(/Every question on this version has an answer/)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await drafting.getByRole("button", { name: "Continue drafting" }).click();

    await expect(drafting.getByRole("status")).toContainText("Version 2");
    expect(asked).toEqual({ version: 1 });
    await page.screenshot({ path: `test-results/continue-drafting-${width}.png`, fullPage: true });
  });
}
