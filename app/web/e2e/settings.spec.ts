/**
 * The Settings page in a browser: the own AI account (docs/specs/model-accounts.md, Enrolment)
 * with axe in both schemes and added and removed by keyboard alone, the preferences, and the way
 * there from the banner and the Profile page.
 *
 * `/api/session` and `/api/model-account/ticket` are answered from the fixtures
 * app/tests/test_sign_in.py and app/tests/test_model_account.py keep current, and so is the model
 * broker's `/broker/enrolment/account`.
 */

import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

import held from "../fixtures/model-account.json" with { type: "json" };
import none from "../fixtures/model-account-none.json" with { type: "json" };
import rejected from "../fixtures/model-account-rejected.json" with { type: "json" };
import ticket from "../fixtures/model-account-ticket.json" with { type: "json" };
import signedIn from "../fixtures/session-signed-in.json" with { type: "json" };

const KEY = "sk-ant-api03-typed-by-keyboard-5678";

const ORIGIN = "https://llm.example.ac.uk";
const OFFERED = [
  { provider: "anthropic", base_urls: [] },
  { provider: "openai", base_urls: [] },
  { provider: "openai-compatible", base_urls: [ORIGIN] },
];

/** A signed-in person on a deployment that offers own accounts, whose account starts as `start`.
 * `sent` collects each enrolment's body. */
async function serve(
  page: Page,
  start: unknown,
  enrolled: { status: number; json: unknown },
  providers: unknown[] = [{ provider: "anthropic", base_urls: [] }],
  sent: unknown[] = [],
) {
  let account = start;
  await page.route("/api/session", (route) =>
    route.fulfill({
      json: {
        ...signedIn,
        model_accounts: true,
        model_account_providers: providers,
      },
    }),
  );
  await page.route("/api/model-account/ticket", (route) =>
    route.fulfill({ json: ticket }),
  );
  await page.route("/broker/enrolment/account", async (route) => {
    const request = route.request();
    expect(request.headers()["authorization"]).toBe(`Bearer ${ticket.ticket}`);
    switch (request.method()) {
      case "PUT":
        sent.push(request.postDataJSON());
        if (enrolled.status === 200) account = enrolled.json;
        return route.fulfill(enrolled);
      case "DELETE":
        account = none;
        return route.fulfill({ status: 204 });
      default:
        return route.fulfill({ json: account });
    }
  });
}

async function useScheme(page: Page, scheme: "light" | "dark") {
  await page.addInitScript(
    (value) => localStorage.setItem("dd-theme", value),
    scheme,
  );
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations;
}

for (const scheme of ["light", "dark"] as const) {
  test(`settings with a choice of providers, ${scheme}: no axe violations`, async ({
    page,
  }) => {
    await useScheme(page, scheme);
    await serve(page, none, { status: 200, json: held }, OFFERED);
    await page.goto("/settings");
    await page
      .getByRole("radio", { name: "A model service your institution runs" })
      .check();
    await expect(page.getByLabel("Address of the service")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });

  for (const [name, start] of [
    ["no account", none],
    ["an account", held],
  ] as const) {
    test(`settings with ${name}, ${scheme}: no axe violations against WCAG 2.2 AA`, async ({
      page,
    }) => {
      await useScheme(page, scheme);
      await serve(page, start, { status: 200, json: held });
      await page.goto("/settings");
      await expect(
        page.getByRole("heading", { name: "Your AI account" }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Your token use" }),
      ).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
    });
  }
}

test("an account is added and removed by keyboard alone", async ({ page }) => {
  await serve(page, none, { status: 200, json: held });
  await page.goto("/settings");
  const field = page.getByLabel("Anthropic API key");
  await field.focus();
  await page.keyboard.type(KEY);
  await page.keyboard.press("Enter");

  await expect(
    page.getByRole("status").filter({ hasText: "checked and saved" }),
  ).toBeVisible();
  await expect(page.getByText(held.account.label)).toBeVisible();
  await expect(page.getByText(KEY)).toHaveCount(0);

  const remove = page.getByRole("button", { name: "Remove account" });
  await remove.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
  await dialog.getByRole("button", { name: "Remove account" }).focus();
  await page.keyboard.press("Enter");

  await expect(
    page.getByRole("status").filter({ hasText: "removed" }),
  ).toBeVisible();
  await expect(page.getByLabel("Anthropic API key")).toBeVisible();
});

test("a key the provider refuses is explained and not kept on the page", async ({
  page,
}) => {
  await serve(page, none, { status: 422, json: rejected });
  await page.goto("/settings");
  const field = page.getByLabel("Anthropic API key");
  await field.fill(KEY);
  await page.getByRole("button", { name: "Check and add" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "did not accept this key",
  );
  await expect(field).toHaveValue("");
});

test("an OpenAI-compatible account is chosen and added by keyboard alone", async ({
  page,
}) => {
  const sent: unknown[] = [];
  await serve(page, none, { status: 200, json: held }, OFFERED, sent);
  await page.goto("/settings");
  const first = page.getByRole("radio", { name: "Anthropic" });
  await first.focus();
  // Arrow keys move through a radio group and choose as they go.
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("radio", { name: "A model service your institution runs" }),
  ).toBeChecked();

  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Address of the service")).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.type("/v1");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("API key for the service")).toBeFocused();
  await page.keyboard.type(KEY);
  await page.keyboard.press("Enter");

  await expect(
    page.getByRole("status").filter({ hasText: "checked and saved" }),
  ).toBeVisible();
  expect(sent).toEqual([
    { provider: "openai-compatible", key: KEY, base_url: `${ORIGIN}/v1` },
  ]);
});

test("preferences apply at once, survive a reload and can match the device", async ({
  page,
}) => {
  await page.emulateMedia({
    colorScheme: "dark",
    reducedMotion: "no-preference",
  });
  await serve(page, none, { status: 200, json: held });
  await page.goto("/settings");
  await page.getByRole("tab", { name: "Appearance" }).click();
  const html = page.locator("html");
  const rootStyle = (property: string) =>
    page.evaluate(
      (p) => getComputedStyle(document.documentElement).getPropertyValue(p),
      property,
    );

  // Light by default, whatever the device prefers.
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.getByRole("radio", { name: "Match my device" }).first().check();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Dark mode" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.emulateMedia({ colorScheme: "light" });
  await expect(html).toHaveAttribute("data-theme", "light");

  await page.getByRole("radio", { name: "Larger" }).check();
  expect(await rootStyle("font-size")).toBe("20px");
  await page.getByRole("radio", { name: "Reduce" }).check();
  expect((await rootStyle("--duration-fast")).trim()).toMatch(/^0m?s$/);

  await page.reload();
  await expect(page.getByRole("radio", { name: "Larger" })).toBeChecked();
  await expect(html).toHaveAttribute("data-text-size", "larger");
  await expect(html).toHaveAttribute("data-motion", "reduce");
  expect(await axeViolations(page)).toEqual([]);
});

test("the cog in the banner and the Profile page both lead to the settings", async ({
  page,
}) => {
  await serve(page, none, { status: 200, json: held });
  await page.goto("/profile");
  expect(await axeViolations(page)).toEqual([]);
  await page.getByRole("main").getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Settings" }),
  ).toBeVisible();
  const cog = page.getByRole("banner").getByRole("link", { name: "Settings" });
  await expect(cog).toHaveAttribute("aria-current", "page");
});
