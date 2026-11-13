import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import held from "../../../fixtures/model-account.json";
import none from "../../../fixtures/model-account-none.json";
import rejected from "../../../fixtures/model-account-rejected.json";
import {
  AccountRefused,
  type ModelAccountApi,
  ModelAccountApiContext,
  type RawModelAccount,
  fromRaw,
} from "../../model-account/api";
import { ModelAccount } from "./ModelAccount";

const NONE = fromRaw(none as RawModelAccount);
const HELD = fromRaw(held as RawModelAccount);
const KEY = "sk-ant-api03-typed-in-the-page-1234";
const LABEL = held.account.label;
const FIRST_MODEL = held.usage[0]?.model ?? "";

function fakeApi(overrides: Partial<ModelAccountApi> = {}): ModelAccountApi {
  return {
    read: () => Promise.resolve(NONE),
    enrol: () => Promise.resolve(HELD),
    remove: () => Promise.resolve(),
    ...overrides,
  };
}

function renderWith(api: ModelAccountApi) {
  return render(
    <ModelAccountApiContext.Provider value={api}>
      <ModelAccount />
    </ModelAccountApiContext.Provider>,
  );
}

describe("ModelAccount", () => {
  it("adds a key the provider accepts and shows only its label", async () => {
    const enrol = vi.fn(() => Promise.resolve(HELD));
    renderWith(fakeApi({ enrol }));
    const field = await screen.findByLabelText("Anthropic API key");
    expect(field).toHaveAttribute("type", "password");

    await userEvent.type(field, KEY);
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));

    expect(enrol).toHaveBeenCalledWith("anthropic", KEY);
    expect(await screen.findByRole("status")).toHaveTextContent(/checked and saved/);
    expect(screen.getByText(LABEL)).toBeVisible();
    expect(screen.queryByLabelText("Anthropic API key")).toBeNull();
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("says in plain words why a key was refused, and clears it", async () => {
    const reason = (rejected as { reason: string }).reason;
    renderWith(fakeApi({ enrol: () => Promise.reject(new AccountRefused(reason)) }));
    const field = await screen.findByLabelText("Anthropic API key");
    await userEvent.type(field, KEY);
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/did not accept this key/);
    expect(field).toHaveValue("");
  });

  it("shows the account's label and the person's token use", async () => {
    renderWith(fakeApi({ read: () => Promise.resolve(HELD) }));
    expect(await screen.findByText(LABEL)).toBeVisible();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(HELD.usage.length + 1);
    expect(within(table).getByText(FIRST_MODEL)).toBeVisible();
  });

  it("removes the account once the person confirms", async () => {
    const remove = vi.fn(() => Promise.resolve());
    renderWith(fakeApi({ read: () => Promise.resolve(HELD), remove }));
    await userEvent.click(await screen.findByRole("button", { name: "Remove account" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove account" }));

    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    expect(await screen.findByLabelText("Anthropic API key")).toBeVisible();
    expect(screen.queryByText(LABEL)).toBeNull();
  });

  it("keeps the account if the person thinks better of it", async () => {
    const remove = vi.fn(() => Promise.resolve());
    renderWith(fakeApi({ read: () => Promise.resolve(HELD), remove }));
    await userEvent.click(await screen.findByRole("button", { name: "Remove account" }));
    await userEvent.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(remove).not.toHaveBeenCalled();
  });

  it("has no accessibility violations, with or without an account", async () => {
    const { container, unmount } = renderWith(fakeApi());
    await screen.findByLabelText("Anthropic API key");
    expect(await axe(container)).toHaveNoViolations();
    unmount();
    const second = renderWith(fakeApi({ read: () => Promise.resolve(HELD) }));
    await screen.findByText(LABEL);
    expect(await axe(second.container)).toHaveNoViolations();
  });
});
