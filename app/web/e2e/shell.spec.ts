/**
 * The built shell in a browser: axe, keyboard-only use, and reflow at the 400% zoom equivalent.
 *
 * `/api/agents` and `/api/process-flow` are answered from the fixtures app/tests/test_app.py
 * keeps current.
 */

import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

import empty from "../../config/examples/empty.profile.json" with { type: "json" };
import soil from "../../config/examples/soil-chemistry.profile.json" with { type: "json" };
import reference from "../fixtures/agents.json" with { type: "json" };
import several from "../fixtures/agents-several.json" with { type: "json" };
import conversation from "../fixtures/conversation.json" with { type: "json" };
import flow from "../fixtures/process-flow.json" with { type: "json" };
import turn from "../fixtures/conversation-turn.json" with { type: "json" };
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

/** Answer the shell's API from the fixtures: the agents, the phases, the examples, and a run. */
async function serve(page: Page, body: unknown, run: unknown = succeeded) {
  await page.route("/api/agents", (route) => route.fulfill({ json: body }));
  await page.route("/api/process-flow", (route) => route.fulfill({ json: flow }));
  await page.route("/api/examples", (route) => route.fulfill({ json: EXAMPLES }));
  await page.route("/api/runs", (route) =>
    route.fulfill({ json: route.request().method() === "POST" ? run : [row(succeeded)] }),
  );
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
}

/** The directory is its own page, `/agents`. */
async function gotoDirectory(page: Page) {
  await page.goto("/agents");
}

/** The several-agents set plus an orchestrator, named by the profile (ADR-0024 §10). */
const withOrchestrator = {
  ...several,
  profile: { ...several.profile, orchestrator: "director.stub" },
  agents: [
    ...several.agents,
    { ...several.agents[0], agent_id: "director.stub", grounding_mode: "delegation" },
  ],
};

async function serveConversation(page: Page) {
  await serve(page, withOrchestrator);
  await page.route("/api/conversations", (route) =>
    route.fulfill(
      route.request().method() === "POST"
        ? { status: 201, json: { conversation_id: conversation.conversation_id } }
        : { json: [] },
    ),
  );
  await page.route("/api/conversations/*/turns", (route) =>
    route.fulfill({ status: 201, json: turn }),
  );
  await page.route("/api/conversations/*", (route) => route.fulfill({ json: conversation }));
}

/** Choose the scheme as the banner's switch would, before the page loads. */
async function useScheme(page: Page, scheme: "light" | "dark") {
  await page.addInitScript((value) => localStorage.setItem("dd-theme", value), scheme);
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
      await useScheme(page, scheme);
      await serve(page, body);
      await gotoDirectory(page);
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
  await gotoDirectory(page);
  await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
  // The skip link is the first stop on every page.
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();

  // The directory is one link away; its list is one stop for the keyboard.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Agents" }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await page.getByRole("option", { name: "hello.world" }).focus();
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
  await gotoDirectory(page);
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
  await gotoDirectory(page);
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
      await useScheme(page, scheme);
      await serve(page, reference, run);
      await gotoDirectory(page);
      await page.getByRole("button", { name: "Run", exact: true }).click();
      await expect(page.getByRole("heading", { name: /^Outcome:/ })).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
    });
  }
}

test("a run and the history reflow at 320 CSS pixels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serve(page, reference);
  await gotoDirectory(page);
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

for (const scheme of ["light", "dark"] as const) {
  test(`conversation home, ${scheme}: no axe violations against WCAG 2.2 AA`, async ({ page }) => {
    await useScheme(page, scheme);
    await serveConversation(page);
    await page.goto("/");
    await page.getByRole("textbox", { name: "What would you like to do?" }).fill("hello world");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByRole("list", { name: "Conversation" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });
}

test("conversation: keyboard only, focus returns to the message box, reflows at 320px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "What would you like to do?" });
  await box.focus();
  await page.keyboard.type("hello world");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Send" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Conversation" })).toBeVisible();
  await expect(box).toBeFocused();
  expect(await overflow(page), "horizontal overflow on the conversation").toBeLessThanOrEqual(0);
});

test("a delegated run is its own view at 320px, reached from the card, and Back returns to it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
  await page.goto("/");
  await page.getByRole("textbox", { name: "What would you like to do?" }).fill("hello world");
  await page.getByRole("button", { name: "Send" }).click();
  const open = page.getByRole("button", { name: /Open run/ }).first();
  await open.click();
  await expect(page).toHaveURL(/\?run=/);
  await expect(page.getByRole("heading", { name: /^Run of / })).toBeFocused();
  await expect(page.getByRole("list", { name: "Conversation" })).toBeHidden();
  expect(await overflow(page), "horizontal overflow on the run view").toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Back to the conversation" }).click();
  await expect(open).toBeFocused();
});

test("the directory is a page: reachable from the navigation, survives a reload, and Back leaves it", async ({
  page,
}) => {
  await serve(page, several);
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await nav.getByRole("link", { name: "Agents" }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(nav.getByRole("link", { name: "Agents" })).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(nav.getByRole("link", { name: "Conversation" })).toHaveAttribute("aria-current", "page");
});

for (const width of [1280, 320]) {
  test(`at ${width}px the banner does not move between pages or tabs`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await serveConversation(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    const parts = [nav, page.getByRole("button", { name: "Dark mode" })];
    const boxes = () => Promise.all(parts.map((part) => part.boundingBox()));

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const first = await boxes();

    await nav.getByRole("link", { name: "Agents" }).click();
    await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
    expect(await boxes(), "after opening Agents").toEqual(first);

    for (const tab of ["About", "History", "Run"]) {
      await page.getByRole("tab", { name: tab }).click();
      expect(await boxes(), `after selecting ${tab}`).toEqual(first);
    }
  });
}

test("a link names the agent to show", async ({ page }) => {
  await serve(page, several);
  await page.goto("/agents?agent=quality.reviewer");
  await expect(page.getByRole("heading", { level: 2, name: "quality.reviewer" })).toBeVisible();
});

test("the workspace at 1280px: phases, conversation and the open run side by side", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await serveConversation(page);
  await page.goto("/");
  const phases = page.getByRole("navigation", { name: "Blueprint phases" });
  await expect(phases.locator("summary")).toHaveCount(6);
  await expect(page.getByRole("region", { name: "Runs and evidence" })).toBeVisible();
  expect(await overflow(page), "horizontal overflow on the workspace").toBeLessThanOrEqual(0);

  // A phase opens from the keyboard and names the agents serving its steps.
  const first = phases.locator("summary").first();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(phases.getByRole("link", { name: "standards.advisor" }).first()).toBeVisible();

  // An open run sits beside the transcript, and closing it returns focus to its card.
  await page.getByRole("textbox", { name: "What would you like to do?" }).fill("hello world");
  await page.getByRole("button", { name: "Send" }).click();
  const open = page.getByRole("button", { name: /Open run/ }).first();
  await open.click();
  await expect(page.getByRole("heading", { name: /^Run of / })).toBeFocused();
  await expect(page.getByRole("list", { name: "Conversation" })).toBeVisible();
  await expect(phases).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
  await page.getByRole("button", { name: "Back to the conversation" }).click();
  await expect(open).toBeFocused();
  await expect(page.getByRole("region", { name: "Runs and evidence" })).toBeVisible();
});

test("the workspace reflows at 320px with every phase open", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.goto("/");
  const summaries = page.getByRole("navigation", { name: "Blueprint phases" }).locator("summary");
  await expect(summaries).toHaveCount(6);
  for (const summary of await summaries.all()) await summary.click();
  expect(await overflow(page), "horizontal overflow with the phases open").toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);
});

test("light by default whatever the system prefers; the dark choice survives a reload", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await serveConversation(page);
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(await background()).toBe("rgb(255, 255, 255)");

  await page.getByRole("button", { name: "Dark mode" }).click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Dark mode" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
  expect(await background()).not.toBe("rgb(255, 255, 255)");
});

for (const scheme of ["light", "dark"] as const) {
  test(`report a problem, ${scheme}: sends with the version, no axe violations`, async ({ page }) => {
    await useScheme(page, scheme);
    await serve(page, reference);
    await page.route("/api/about", (route) =>
      route.fulfill({
        json: {
          app_version: "0.3.0-alpha.1",
          harness_version: "0.1.0",
          commit: "abcdef0123456789",
          feedback_enabled: true,
        },
      }),
    );
    let sent: Record<string, unknown> | undefined;
    await page.route("/api/feedback", (route) => {
      sent = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 201,
        json: { url: "https://github.com/data-director-agent/data-director/issues/1", number: 1 },
      });
    });
    await page.goto("/agents");
    await page.getByRole("link", { name: "Report a problem" }).click();
    await expect(page.getByText("This is Data Director v0.3.0-alpha.1 (abcdef0).")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await page.getByLabel("Title").fill("It hangs");
    await page.getByLabel("Details").fill("Never ends.");
    await page.getByRole("button", { name: "Send report" }).click();
    await expect(page.getByRole("status")).toContainText("issue #1");
    expect(sent).toMatchObject({ kind: "bug", title: "It hangs", page: "/agents" });
    expect(await axeViolations(page)).toEqual([]);
  });
}
