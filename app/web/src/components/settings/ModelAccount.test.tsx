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
import type { ModelAccountProvider } from "../../session/api";
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

const ORIGIN = "https://llm.example.ac.uk";
const OFFERED: ModelAccountProvider[] = [
  { provider: "anthropic", baseUrls: [] },
  { provider: "openai", baseUrls: [] },
  { provider: "openai-compatible", baseUrls: [ORIGIN] },
];

function renderWith(api: ModelAccountApi, providers?: ModelAccountProvider[]) {
  return render(
    <ModelAccountApiContext.Provider value={api}>
      <ModelAccount {...(providers ? { providers } : {})} />
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

  it("offers no choice of provider where the profile allows one", async () => {
    renderWith(fakeApi(), [{ provider: "openai", baseUrls: [] }]);
    expect(await screen.findByLabelText("OpenAI API key")).toBeVisible();
    expect(screen.queryByRole("group", { name: "Provider" })).toBeNull();
  });

  it("offers the providers the profile allows, and sends no address for a hosted one", async () => {
    const enrol = vi.fn(() => Promise.resolve(HELD));
    renderWith(fakeApi({ enrol }), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    expect(within(group).getAllByRole("radio")).toHaveLength(OFFERED.length);

    await userEvent.click(within(group).getByRole("radio", { name: "OpenAI" }));
    await userEvent.type(screen.getByLabelText("OpenAI API key"), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));

    expect(enrol).toHaveBeenCalledWith("openai", KEY);
  });

  it("sends an OpenAI-compatible account's address with its key", async () => {
    const enrol = vi.fn(() => Promise.resolve(HELD));
    renderWith(fakeApi({ enrol }), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    await userEvent.click(within(group).getAllByRole("radio")[2] as HTMLElement);
    const address = screen.getByLabelText("Address of the service");
    expect(address).toHaveValue(ORIGIN);

    await userEvent.type(address, "/v1/");
    await userEvent.type(screen.getByLabelText("API key for the service"), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));

    expect(enrol).toHaveBeenCalledWith("openai-compatible", KEY, `${ORIGIN}/v1`);
  });

  it("sends a key to no address the profile does not list", async () => {
    const enrol = vi.fn(() => Promise.resolve(HELD));
    renderWith(fakeApi({ enrol }), [{ provider: "openai-compatible", baseUrls: [ORIGIN] }]);
    const address = await screen.findByLabelText("Address of the service");
    await userEvent.clear(address);
    await userEvent.type(address, "https://elsewhere.example.org/v1");
    await userEvent.type(screen.getByLabelText("API key for the service"), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));

    expect(enrol).not.toHaveBeenCalled();
    expect(address).toHaveAttribute("aria-invalid", "true");
    expect(address).toHaveAccessibleDescription(expect.stringContaining(ORIGIN));
  });

  it("has no accessibility violations with a choice of providers", async () => {
    const { container } = renderWith(fakeApi(), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    await userEvent.click(within(group).getAllByRole("radio")[2] as HTMLElement);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("links to the provider's own page for creating a key, in a new tab", async () => {
    renderWith(fakeApi());
    await screen.findByLabelText("Anthropic API key");
    const link = screen.getByRole("link", { name: /Anthropic/ });
    expect(link).toHaveAttribute("href", expect.stringMatching(/^https:\/\//));
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("offers to switch to the provider a key's prefix belongs to, keeping the key", async () => {
    const enrol = vi.fn(() => Promise.resolve(HELD));
    renderWith(fakeApi({ enrol }), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    await userEvent.click(within(group).getByRole("radio", { name: "OpenAI" }));
    await userEvent.type(screen.getByLabelText("OpenAI API key"), KEY);

    const field = screen.getByLabelText("OpenAI API key");
    expect(field).toHaveAccessibleDescription(expect.stringContaining("Anthropic"));
    await userEvent.click(screen.getByRole("button", { name: /Anthropic/ }));

    expect(within(group).getByRole("radio", { name: "Anthropic" })).toBeChecked();
    expect(screen.getByLabelText("Anthropic API key")).toHaveValue(KEY);
    expect(screen.queryByRole("button", { name: /Anthropic/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Check and add" }));
    expect(enrol).toHaveBeenCalledWith("anthropic", KEY);
  });

  it("suggests no provider the profile does not allow, nor one for an institution's service", async () => {
    renderWith(fakeApi(), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    await userEvent.type(screen.getByLabelText("Anthropic API key"), "AIza-not-offered-here");
    expect(screen.queryByRole("button", { name: /instead/ })).toBeNull();

    await userEvent.click(within(group).getAllByRole("radio")[2] as HTMLElement);
    await userEvent.type(screen.getByLabelText("API key for the service"), KEY);
    expect(screen.queryByRole("button", { name: /instead/ })).toBeNull();
  });

  it("has no accessibility violations while it suggests another provider", async () => {
    const { container } = renderWith(fakeApi(), OFFERED);
    const group = await screen.findByRole("group", { name: "Provider" });
    await userEvent.click(within(group).getByRole("radio", { name: "OpenAI" }));
    await userEvent.type(screen.getByLabelText("OpenAI API key"), KEY);
    await screen.findByRole("button", { name: /Anthropic/ });
    expect(await axe(container)).toHaveNoViolations();
  });
});
