import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import {
  type DepositApi,
  DepositApiContext,
  type RepositoryAccount as Account,
  RepositoryAccountRefused,
} from "../../deposit/api";
import { RepositoryAccount, repositoryName, returned } from "./RepositoryAccount";

const SANDBOX = "https://sandbox.zenodo.org/api";
const NOT_CONNECTED: Account = { baseUrl: SANDBOX, connected: false };
const CONNECTED: Account = {
  baseUrl: SANDBOX,
  connected: true,
  label: "Signed in at sandbox.zenodo.org",
  method: "oauth",
  created: "2026-11-20T10:00:00+00:00",
};

function renderAccount(api: Partial<DepositApi>, search = "") {
  const full = {
    options: () => Promise.resolve([{ baseUrl: SANDBOX, transport: "zenodo", oauth: true }]),
    account: () => Promise.resolve(NOT_CONNECTED),
    ...api,
  } as DepositApi;
  return render(
    <DepositApiContext.Provider value={full}>
      <RepositoryAccount search={search} />
    </DepositApiContext.Provider>,
  );
}

describe("repositoryName", () => {
  it("names the Zenodo sandbox apart from Zenodo", () => {
    expect(repositoryName(SANDBOX)).toBe("Zenodo sandbox");
    expect(repositoryName("https://zenodo.org/api")).toBe("Zenodo");
  });
});

describe("returned", () => {
  it("reads what coming back from the repository says", () => {
    expect(returned("?repository=connected")).toEqual({
      ok: true,
      message: "Your repository account is connected.",
    });
    expect(returned("?repository_error=account-rejected")?.ok).toBe(false);
    expect(returned("")).toBeNull();
  });
});

describe("RepositoryAccount", () => {
  it("offers to connect through the repository, or with a token", async () => {
    const connect = vi.fn(() => Promise.resolve());
    const { container } = renderAccount({ connect });
    const button = await screen.findByRole("button", { name: "Connect your Zenodo sandbox account" });
    expect(screen.getByText(/records and DOIs are not real/)).toBeInTheDocument();
    expect(screen.getByText("Or paste a personal token")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(button);
    expect(connect).toHaveBeenCalledWith("zenodo", SANDBOX);
  });

  it("saves a pasted token and shows only its label", async () => {
    const saveToken = vi.fn(() =>
      Promise.resolve({ ...CONNECTED, method: "token" as const, label: "Personal token ending abcd" }),
    );
    renderAccount({ saveToken });
    await userEvent.click(await screen.findByText("Or paste a personal token"));
    await userEvent.type(screen.getByLabelText("Personal access token"), "secret-token-abcd");
    await userEvent.click(screen.getByRole("button", { name: "Save the token" }));
    expect(saveToken).toHaveBeenCalledWith(SANDBOX, "secret-token-abcd");
    expect(await screen.findByText("Personal token ending abcd")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("secret-token-abcd")).not.toBeInTheDocument();
  });

  it("says why a token was not saved", async () => {
    renderAccount({
      saveToken: () => Promise.reject(new RepositoryAccountRefused("account-rejected")),
    });
    await userEvent.click(await screen.findByText("Or paste a personal token"));
    await userEvent.type(screen.getByLabelText("Personal access token"), "wrong-token");
    await userEvent.click(screen.getByRole("button", { name: "Save the token" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("did not accept your account");
  });

  it("shows a connected account and disconnects it", async () => {
    const disconnect = vi.fn(() => Promise.resolve());
    renderAccount({ account: () => Promise.resolve(CONNECTED), disconnect });
    expect(await screen.findByText("Signed in at sandbox.zenodo.org")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Disconnect Zenodo sandbox" }));
    expect(disconnect).toHaveBeenCalledWith(SANDBOX);
    expect(await screen.findByText(/was disconnected/)).toBeInTheDocument();
  });

  it("says the account was connected on coming back from the repository", async () => {
    renderAccount({}, "?repository=connected");
    expect(await screen.findByText("Your repository account is connected.")).toBeInTheDocument();
  });
});
