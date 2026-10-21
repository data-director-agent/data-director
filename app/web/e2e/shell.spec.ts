/**
 * The built shell in a browser: axe, keyboard-only use, and reflow at the 400% zoom equivalent.
 *
 * `/api/agents` is answered from the fixtures app/tests/test_app.py keeps current.
 */

import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

import empty from "../../config/examples/empty.profile.json" with { type: "json" };
import soil from "../../config/examples/soil-chemistry.profile.json" with { type: "json" };
import reference from "../fixtures/agents.json" with { type: "json" };
import several from "../fixtures/agents-several.json" with { type: "json" };
import abstained from "../fixtures/run-abstained.json" with { type: "json" };
import succeeded from "../fixtures/run-succeeded.json" with { type: "json" };

const EXAMPLES = [
  { name: "empty.profile", schema_class: "DatasetProfile", input: empty },
  { name: "soil-chemistry.profile", schema_class: "DatasetProfile", input: soil },
];

function row(run: typeof succeeded | typeof abstained) {
  const { envelope } = run;
  return {
    invocation_id: envelope.invocation_id,
    agent_id: envelope.agent_id,
    status: envelope.outcome.status,
    completed_at: envelope.completed_at,
    acting_for: envelope.acting_for.name,
  };
}

/** Answer the shell's API from the fixtures: the agents, the examples, and a run's result. */
async function serve(page: Page, body: unknown, run: unknown = succeeded) {
  await page.route("/api/agents", (route) => route.fulfill({ json: body }));
  await page.route("/api/examples", (route) => route.fulfill({ json: EXAMPLES }));
  await page.route("/api/runs", (route) =>
    route.fulfill({ json: route.request().method() === "POST" ? run : [row(succeeded)] }),
  );
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations;
}

async function overflow(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

for (const [name, body] of [
  ["reference set", reference],
  ["several agents", several],
] as const) {
  for (const scheme of ["light", "dark"] as const) {
    test(`${name}, ${scheme}: no axe violations against WCAG 2.2 AA`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await serve(page, body);
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
}

test("keyboard only: skip link, then the agent list, then the selected agent", async ({ page }) => {
  await serve(page, several);
  await page.goto("/");
  await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("option", { name: "hello.world" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "quality.reviewer" })).toBeFocused();
  await expect(page.getByRole("heading", { level: 2, name: "quality.reviewer" })).toBeVisible();

  // Tab leaves the listbox rather than walking every option: one stop per widget.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("option")).not.toHaveCount(0);
  for (const option of await page.getByRole("option").all()) {
    await expect(option).not.toBeFocused();
  }
});

test("reflows at 320 CSS pixels (400% of 1280) without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serve(page, several);
  await page.goto("/");
  await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
  for (const option of ["quality.reviewer", "standards.advisor", "stub.abstain"]) {
    await page.getByRole("option", { name: option }).click();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow with ${option} selected`).toBeLessThanOrEqual(0);
  }
});

test("a server failure is announced as an alert", async ({ page }) => {
  await page.route("/api/agents", (route) => route.fulfill({ status: 500, body: "" }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("the server answered 500");
});

test("keyboard only: load an example, run it, and land on the outcome", async ({ page }) => {
  await serve(page, reference);
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Run" })).toHaveAttribute("aria-selected", "true");

  const load = page.getByRole("button", { name: "Load example: soil chemistry profile" });
  await load.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Title")).toHaveValue(soil.title);

  await page.getByRole("button", { name: "Run", exact: true }).focus();
  await page.keyboard.press("Enter");
  const outcome = page.getByRole("heading", { name: "Outcome: Succeeded" });
  await expect(outcome).toBeFocused();

  // A "rests on" link moves to the evidence it names.
  const link = page.getByRole("table").getByRole("link").first();
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".evidence-list > li:target")).toHaveCount(1);
});

for (const [name, run] of [
  ["succeeded", succeeded],
  ["abstained", abstained],
] as const) {
  for (const scheme of ["light", "dark"] as const) {
    test(`run outcome ${name}, ${scheme}: no axe violations against WCAG 2.2 AA`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await serve(page, reference, run);
      await page.goto("/");
      await page.getByRole("button", { name: "Run", exact: true }).click();
      await expect(page.getByRole("heading", { name: /^Outcome:/ })).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
    });
  }
}

test("a run and the history reflow at 320 CSS pixels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serve(page, reference);
  await page.goto("/");
  await page.getByRole("button", { name: "Load example: soil chemistry profile" }).click();
  expect(await overflow(page), "horizontal overflow on the form").toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Outcome: Succeeded" })).toBeVisible();
  expect(await overflow(page), "horizontal overflow on the outcome").toBeLessThanOrEqual(0);

  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByRole("heading", { name: "Runs of this agent" })).toBeVisible();
  expect(await overflow(page), "horizontal overflow on the history").toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);
});
