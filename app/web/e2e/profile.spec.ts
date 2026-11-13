/**
 * The Profile page's own AI account in a browser (docs/specs/model-accounts.md, Enrolment): axe in
 * both schemes, and adding and removing an account by keyboard alone.
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

/** A signed-in person on a deployment that offers own accounts, whose account starts as `start`. */
async function serve(page: Page, start: unknown, enrolled: { status: number; json: unknown }) {
  let account = start;
  await page.route("/api/session", (route) =>
    route.fulfill({ json: { ...signedIn, model_accounts: true } }),
  );
  await page.route("/api/model-account/ticket", (route) => route.fulfill({ json: ticket }));
  await page.route("/broker/enrolment/account", async (route) => {
    const request = route.request();
    expect(request.headers()["authorization"]).toBe(`Bearer ${ticket.ticket}`);
    switch (request.method()) {
      case "PUT":
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
  await page.addInitScript((value) => localStorage.setItem("dd-theme", value), scheme);
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations;
}

for (const scheme of ["light", "dark"] as const) {
  for (const [name, start] of [
    ["no account", none],
    ["an account", held],
  ] as const) {
    test(`profile with ${name}, ${scheme}: no axe violations against WCAG 2.2 AA`, async ({
      page,
    }) => {
      await useScheme(page, scheme);
      await serve(page, start, { status: 200, json: held });
      await page.goto("/profile");
      await expect(page.getByRole("heading", { name: "Your AI account" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Your token use" })).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
    });
  }
}

test("an account is added and removed by keyboard alone", async ({ page }) => {
  await serve(page, none, { status: 200, json: held });
  await page.goto("/profile");
  const field = page.getByLabel("Anthropic API key");
  await field.focus();
  await page.keyboard.type(KEY);
  await page.keyboard.press("Enter");

  await expect(page.getByRole("status").filter({ hasText: "checked and saved" })).toBeVisible();
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

  await expect(page.getByRole("status").filter({ hasText: "removed" })).toBeVisible();
  await expect(page.getByLabel("Anthropic API key")).toBeVisible();
});

test("a key the provider refuses is explained and not kept on the page", async ({ page }) => {
  await serve(page, none, { status: 422, json: rejected });
  await page.goto("/profile");
  const field = page.getByLabel("Anthropic API key");
  await field.fill(KEY);
  await page.getByRole("button", { name: "Check and add" }).click();
  await expect(page.getByRole("alert")).toContainText("did not accept this key");
  await expect(field).toHaveValue("");
});
