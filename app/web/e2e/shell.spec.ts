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
import answered from "../fixtures/conversation-answered.json" with { type: "json" };
import question from "../fixtures/conversation-question.json" with { type: "json" };
import flow from "../fixtures/process-flow.json" with { type: "json" };
import project from "../fixtures/project-documents.json" with { type: "json" };
import disclosure from "../fixtures/project-disclosure.json" with { type: "json" };
import projects from "../fixtures/projects.json" with { type: "json" };
import turn from "../fixtures/conversation-turn.json" with { type: "json" };
import abstained from "../fixtures/run-abstained.json" with { type: "json" };
import succeeded from "../fixtures/run-succeeded.json" with { type: "json" };
import development from "../fixtures/session-development.json" with { type: "json" };
import signedIn from "../fixtures/session-signed-in.json" with { type: "json" };
import signedOut from "../fixtures/session-signed-out.json" with { type: "json" };

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

/** Who is signed in. Unless a test says otherwise, a development server: nobody signs in. */
async function serveSession(page: Page, session: unknown) {
  await page.route("/api/session", (route) => route.fulfill({ json: session }));
}

test.beforeEach(async ({ page }) => {
  await serveSession(page, development);
});

/** The directory is its own page, `/agents`. */
async function gotoDirectory(page: Page) {
  await page.goto("/agents");
}

/** The several-agents set plus an orchestrator, named by the profile (docs/specs/app.md). */
const withOrchestrator = {
  ...several,
  profile: { ...several.profile, orchestrator: "orchestrator.stub" },
  agents: [
    ...several.agents,
    { ...several.agents[0], agent_id: "orchestrator.stub", grounding_mode: "delegation" },
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
  await page.getByRole("option", { name: "Metadata Reviewer" }).focus();
  await expect(page.getByRole("option", { name: "Metadata Reviewer" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "Standards Librarian" })).toBeFocused();
  await expect(page.getByRole("heading", { level: 2, name: "Standards Librarian" })).toBeVisible();

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
  for (const option of ["Metadata Reviewer", "Standards Librarian", "stub.abstain"]) {
    await page.getByRole("option", { name: option }).click();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow with ${option} selected`).toBeLessThanOrEqual(0);
  }
});

test("a project's document is rejected with the keyboard alone, at 320px, and the result announced", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  // The fixture's README, proposed, and its data dictionary, approved.
  const [readme, dictionary] = project.documents;
  const draft = readme?.versions[0];
  if (!readme || !draft) throw new Error("the fixture has no README draft");
  const rejected = {
    ...project,
    documents: [
      {
        ...readme,
        versions: [
          {
            ...draft,
            state: "rejected",
            decision: { reason: "No site named.", decided_by: draft.added_by, decided_at: draft.added_at },
          },
        ],
      },
      dictionary,
    ],
    decided: { document_id: readme.document_id, version: 1 },
  };
  const sent: unknown[] = [];
  await page.route(`/api/projects/${project.project_id}/documents`, (route) =>
    route.fulfill({ json: project }),
  );
  await page.route(`/api/projects/${project.project_id}/documents/*/decisions`, (route) => {
    sent.push(route.request().postDataJSON());
    return route.fulfill({ status: 201, json: rejected });
  });
  // At 320px the list comes first, so the README is opened by its address, as a link to it would.
  await page.goto(`/projects/${project.project_id}?doc=${readme.document_id}`);
  const article = page.getByRole("article", { name: "README" });
  await expect(article.getByText("Proposed, not reviewed")).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await article.getByLabel("Approve version 1 as it is").focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(article.getByLabel("Reject version 1")).toBeChecked();
  await page.keyboard.press("Tab");
  await expect(article.getByLabel("Reason (required)")).toBeFocused();
  await page.keyboard.type("No site named.");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");

  // The reader has a live region of its own, for copying, so the page's is found by what it says.
  await expect(page.getByRole("status").filter({ hasText: "README:" })).toContainText(
    "README: version 1 rejected.",
  );
  await expect(article.getByRole("heading", { name: "README" })).toBeFocused();
  expect(sent).toEqual([
    { version: 1, digest: draft.digest, decision: "rejected", reason: "No site named." },
  ]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("a server failure is announced as an alert", async ({ page }) => {
  await page.route("/api/agents", (route) => route.fulfill({ status: 500, body: "" }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("the server answered 500");
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
  // Attaching an inventory, and how to make one, come between the message and Send.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Attach inventory" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "How do I make an inventory?" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Send" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Conversation" })).toBeVisible();
  await expect(box).toBeFocused();
  expect(await overflow(page), "horizontal overflow on the conversation").toBeLessThanOrEqual(0);
});

for (const scheme of ["light", "dark"] as const) {
  test(`a choice question, ${scheme}: answered by keyboard at 320px, with no axe violations`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await useScheme(page, scheme);
    await serveConversation(page);
    // Until an answer is sent the conversation ends with the question; then with the answer.
    let sentAnswer: unknown = null;
    await page.route("/api/conversations/*/turns", (route) => {
      sentAnswer = route.request().postDataJSON().choice_answer ?? null;
      return route.fulfill({ status: 201, json: turn });
    });
    await page.route("/api/conversations/*", (route) =>
      route.fulfill({ json: sentAnswer ? answered : question }),
    );
    await page.goto("/");
    const box = page.getByRole("textbox", { name: "What would you like to do?" });
    await box.fill("hi");
    await page.getByRole("button", { name: "Send" }).click();

    const group = page.getByRole("group", { name: "Where are you with your research data?" });
    await expect(group).toBeVisible();
    await expect(page.getByRole("status")).toContainText("It asks you to choose");
    expect(await overflow(page), "horizontal overflow with a question").toBeLessThanOrEqual(0);
    expect(await axeViolations(page)).toEqual([]);

    await group.getByRole("radio").first().focus();
    await page.keyboard.press("ArrowDown");
    await expect(
      group.getByRole("radio", { name: "Data already collected, being prepared for sharing" }),
    ).toBeChecked();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Send answer" })).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.getByText("(your choice)")).toBeVisible();
    expect(sentAnswer).toEqual({ answer_to: question.turns[0]?.invocation_id, answer_values: ["2"] });
    await expect(box).toBeFocused();
    expect(await axeViolations(page)).toEqual([]);
  });
}

test("an attached inventory shows as a chip, not JSON, at 320px with no axe violations", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.goto("/");
  const inventory = {
    schema_class: "FileInventory",
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0",
    inventory_made_at: "2026-11-01T09:00:00Z",
    inventory_files: Array.from({ length: 42 }, (_, i) => ({
      file_path: `data/file-${i}.csv`,
      file_size: 1200,
      file_sha256: "0".repeat(64),
      file_media_type: "text/csv",
      file_pronom_ids: ["x-fmt/18"],
      file_identified_by: "extension",
      file_fields: [{ name: "site", field_type: "string" }],
    })),
  };
  await page.locator('input[type="file"]').setInputFiles({
    name: "a-long-dataset-inventory-file-name.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(inventory)),
  });
  await expect(page.getByText(/Inventory: 42 files, made 1 Nov 2026/)).toBeVisible();
  await expect(page.getByText("data/file-0.csv")).toHaveCount(0);
  expect(await overflow(page), "horizontal overflow with an inventory attached").toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);

  // Opened in readable form, it fits the width and passes axe; Escape returns to the button.
  const view = page.getByRole("button", { name: "View inventory" });
  await view.press("Enter");
  const dialog = page.getByRole("dialog", { name: "What the inventory holds" });
  await expect(dialog.getByText("42 files, 50.4 kB in all")).toBeVisible();
  // The only top-level folder is open already.
  await expect(dialog.getByText("file-0.csv", { exact: true })).toBeVisible();
  expect(await overflow(page), "horizontal overflow with the inventory open").toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(view).toBeFocused();

  await page.getByRole("button", { name: "Remove inventory" }).press("Enter");
  await expect(page.getByRole("textbox", { name: "What would you like to do?" })).toBeFocused();
});

test("a delegated run opens inside its card at 320px, keeping focus and the conversation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
  await page.goto("/");
  await page.getByRole("textbox", { name: "What would you like to do?" }).fill("hello world");
  await page.getByRole("button", { name: "Send" }).click();
  const toggle = page.getByRole("button", { name: /(Show|Hide) the run/ }).first();
  await toggle.click();
  await expect(page).toHaveURL(/\?run=/);
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation).toBeVisible();
  await expect(conversation.getByRole("heading", { name: /^Outcome:/ })).toBeVisible();
  expect(await overflow(page), "horizontal overflow with a run open").toBeLessThanOrEqual(0);
  await toggle.click();
  await expect(page).not.toHaveURL(/\?run=/);
  await expect(toggle).toBeFocused();
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

test("Projects comes first in the navigation, lists the projects at 320px, and opens one", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await serve(page, several);
  await page.route("/api/projects", (route) => route.fulfill({ json: projects }));
  await page.route("/api/projects/*/documents", (route) => route.fulfill({ json: project }));
  await page.route("/api/projects/*/disclosure", (route) => route.fulfill({ json: disclosure }));
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link").first()).toHaveText("Projects");
  await nav.getByRole("link", { name: "Projects" }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(nav.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  await page.reload();
  const first = page.getByRole("link", { name: "My logger data" });
  await expect(first).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);

  await first.click();
  await expect(page.getByRole("heading", { level: 1, name: "My logger data" })).toBeVisible();
  // At 320px the list and the reader take turns: the list first, then the document chosen.
  const documents = page.getByRole("navigation", { name: "Documents" });
  await documents.getByRole("link", { name: /README/ }).click();
  await expect(page.getByRole("article", { name: "README" })).toBeVisible();
  await expect(documents).toBeHidden();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.getByRole("link", { name: "All documents" }).click();
  await expect(documents).toBeVisible();
  // A project's own page is under Projects.
  await expect(nav.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "All projects" }).click();
  await expect(page).toHaveURL(/\/projects$/);
});

for (const width of [1280, 320]) {
  test(`at ${width}px the banner does not move between pages`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await serveConversation(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    const parts = [nav, page.getByRole("button", { name: "Dark mode" })];
    // Where each part is on the page, not in the viewport: selecting a tab below the fold
    // scrolls the page, which moves nothing in it.
    const boxes = async () => {
      const scrollY = await page.evaluate(() => window.scrollY);
      return (await Promise.all(parts.map((part) => part.boundingBox()))).map(
        (box) => box && { ...box, y: box.y + scrollY },
      );
    };

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const first = await boxes();

    await nav.getByRole("link", { name: "Agents" }).click();
    await expect(page.getByRole("listbox", { name: "Agents" })).toBeVisible();
    expect(await boxes(), "after opening Agents").toEqual(first);
  });
}

test("a link names the agent to show", async ({ page }) => {
  await serve(page, several);
  await page.goto("/agents?agent=advisor.quality");
  await expect(page.getByRole("heading", { level: 2, name: "Metadata Reviewer" })).toBeVisible();
});

test("the workspace at 1280px: conversations, conversation and the project side by side", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await serveConversation(page);
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
  await page.goto("/");
  const phases = page.getByRole("navigation", { name: "Your data journey" });
  await expect(phases.getByRole("list", { name: "The phases in order" }).getByRole("listitem")).toHaveCount(6);
  await expect(page.getByRole("region", { name: "Conversations" })).toBeVisible();
  const documents = page.getByRole("region", { name: "Project" });
  await expect(documents).toBeVisible();
  expect(await overflow(page), "horizontal overflow on the workspace").toBeLessThanOrEqual(0);

  // The strip opens from the keyboard, then a phase, which lists what happens in it.
  const strip = phases.locator(".phase-strip-details > summary");
  await strip.focus();
  await page.keyboard.press("Enter");
  await expect(phases.locator(".phase-list summary")).toHaveCount(6);
  const first = phases.locator(".phase-list summary").first();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(phases.getByText("Choose standard terms to describe your data")).toBeVisible();

  // An open run sits inside its card in the transcript, and the documents stay beside it.
  await page.getByRole("textbox", { name: "What would you like to do?" }).fill("hello world");
  await page.getByRole("button", { name: "Send" }).click();
  const toggle = page.getByRole("button", { name: /(Show|Hide) the run/ }).first();
  await toggle.click();
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation.getByRole("heading", { name: /^Evidence/ })).toBeVisible();
  await expect(toggle).toBeFocused();
  await expect(phases).toBeVisible();
  await expect(documents).toBeVisible();
  expect(await overflow(page), "horizontal overflow with a run open").toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);
  await toggle.click();
  await expect(toggle).toBeFocused();
  await expect(conversation.getByRole("heading", { name: /^Outcome:/ })).toHaveCount(0);
});

test("the workspace reflows at 320px with every phase open", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await serveConversation(page);
  await page.goto("/");
  const phases = page.getByRole("navigation", { name: "Your data journey" });
  await phases.locator(".phase-strip-details > summary").click();
  const summaries = phases.locator(".phase-list summary");
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
    await expect(page.getByRole("contentinfo")).toContainText("v0.3.0-alpha.1 (abcdef0)");
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

// Signing in (docs/specs/policy-and-identity.md). The server decides; the shell shows the sign-in page when it says nobody
// is signed in, or when any request is refused with 401.

test("signed out: the sign-in page, by keyboard, with no axe violations, at 320px", async ({
  page,
}) => {
  await serveSession(page, signedOut);
  await serve(page, reference);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/agents?agent=advisor.standards");
  await expect(
    page.getByRole("heading", { level: 1, name: "Sign in to Data Director" }),
  ).toBeVisible();
  const link = page.getByRole("link", { name: "Sign in with ORCID" });
  await expect(link).toHaveAttribute(
    "href",
    `/api/sign-in?return_to=${encodeURIComponent("/agents?agent=advisor.standards")}`,
  );
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press("Tab");
    if (await link.evaluate((element) => element === document.activeElement)) break;
  }
  await expect(link).toBeFocused();
  expect(await overflow(page)).toBeLessThanOrEqual(0);
  expect(await axeViolations(page)).toEqual([]);
});

test("signed in: the banner names the person, and signing out ends the session", async ({
  page,
}) => {
  await serveSession(page, signedIn);
  await serve(page, reference);
  let signedOutOnServer = false;
  await page.route("/api/sign-out", (route) => {
    signedOutOnServer = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/agents");
  const banner = page.locator("header.app-header");
  await expect(banner.getByText("Josiah Carberry")).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
  await banner.getByRole("button", { name: "Sign out" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "You have signed out" })).toBeVisible();
  await expect(page.getByText(/still be signed in at ORCID/)).toBeVisible();
  expect(signedOutOnServer).toBe(true);
  await expect(banner.getByText("Josiah Carberry")).toHaveCount(0);
  expect(await axeViolations(page)).toEqual([]);
});

test("a request refused with 401 brings the sign-in page back", async ({ page }) => {
  await serveSession(page, signedIn);
  await page.route("/api/agents", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/problem+json",
      json: {
        type: "https://w3id.org/data-director/problems/unauthenticated",
        title: "The caller is not signed in",
        status: 401,
      },
    }),
  );
  await page.goto("/agents");
  await expect(page.getByRole("link", { name: "Sign in with ORCID" })).toBeVisible();
});

test("a sign-in that came back without a session says why", async ({ page }) => {
  await serveSession(page, signedOut);
  await page.goto("/sign-in?problem=declined");
  await expect(page.getByRole("alert")).toContainText("You did not sign in");
  expect(await axeViolations(page)).toEqual([]);
});

test("a development server says in the banner that it signs nobody in", async ({ page }) => {
  await serve(page, reference);
  await page.goto("/agents");
  await expect(page.locator("header.app-header").getByText("Not signing anyone in")).toBeVisible();
  await expect(page.getByText(/asserted by the operator, not authenticated/)).toBeVisible();
});
