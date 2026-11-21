import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import noneFixture from "../../../fixtures/project-deposits-none.json";
import recordedFixture from "../../../fixtures/project-deposit-recorded.json";
import failedFixture from "../../../fixtures/project-deposit-failed.json";
import {
  type DepositApi,
  DepositApiContext,
  DepositRefused,
  type DepositShown,
  type Deposits,
} from "../../deposit/api";
import { DepositToRepository } from "./DepositToRepository";

// What the server says (app/tests/test_deposit_draft.py): a project whose chosen repository,
// Zenodo, the deployment deposits to on the sandbox; then the draft made, or the attempt failed.
const NONE = noneFixture as Deposits;
const RECORDED = recordedFixture as DepositShown;
const FAILED = failedFixture as DepositShown;
const DIGEST = RECORDED.digest;

function renderDraft(api: Partial<DepositApi>) {
  const full = { deposits: () => Promise.resolve(NONE), ...api } as DepositApi;
  return render(
    <DepositApiContext.Provider value={full}>
      <DepositToRepository projectId="p" digest={DIGEST} revision={0} />
    </DepositApiContext.Provider>,
  );
}

describe("DepositToRepository", () => {
  it("says a sandbox deposit is practice, and offers to create a draft", async () => {
    const { container } = renderDraft({});
    expect(
      await screen.findByRole("heading", { name: "Deposit a draft to Zenodo" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Practice deposit/)).toBeInTheDocument();
    expect(screen.getByText(/does not publish the draft/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create a draft in Zenodo" })).toBeEnabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("creates the draft on the person's approval and links to it", async () => {
    const deposit = vi.fn(() => Promise.resolve(RECORDED));
    renderDraft({ deposit });
    await userEvent.click(await screen.findByRole("button", { name: "Create a draft in Zenodo" }));
    expect(deposit).toHaveBeenCalledWith("p", DIGEST);
    expect(await screen.findByRole("link", { name: /Open the draft in Zenodo/ })).toHaveAttribute(
      "href",
      RECORDED.draft_url,
    );
    expect(screen.getByRole("status")).toHaveTextContent("A draft was made in Zenodo");
    expect(screen.getByRole("status")).toHaveTextContent("Sandbox: not a real deposit");
    expect(screen.getAllByText(/Sandbox: not a real deposit/).length).toBeGreaterThan(1);
    expect(screen.queryByRole("button", { name: /Create a draft/ })).not.toBeInTheDocument();
  });

  it("says why no draft was made, and where to connect an account", async () => {
    renderDraft({ deposit: () => Promise.resolve(FAILED) });
    await userEvent.click(await screen.findByRole("button", { name: "Create a draft in Zenodo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You have not connected your repository account yet",
    );
    expect(screen.getByRole("link", { name: /Connect your Zenodo account/ })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("names the earlier draft when the package was already deposited", async () => {
    const refused = new DepositRefused({
      type: "x/already-deposited",
      title: "Nothing was deposited",
      status: 409,
      detail: "this package was already deposited in the repository",
      refusal: "already-deposited",
    });
    renderDraft({ deposit: () => Promise.reject(refused) });
    await userEvent.click(await screen.findByRole("button", { name: "Create a draft in Zenodo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already been deposited");
  });

  it("shows a draft already made for this package", async () => {
    renderDraft({ deposits: () => Promise.resolve({ ...NONE, deposits: [RECORDED] }) });
    expect(await screen.findByRole("link", { name: /Open the draft/ })).toBeInTheDocument();
  });

  it("shows nothing where the repository is deposited to by hand", async () => {
    const byHand: Deposits = {
      connection: {
        repository_name: "Zenodo",
        transport: "zenodo",
        base_url: "https://sandbox.zenodo.org/api",
        sandbox: true,
        available: false,
        unavailable: "transport-not-offered",
      },
      deposits: [],
    };
    const deposits = vi.fn(() => Promise.resolve(byHand));
    const { container } = renderDraft({ deposits });
    await vi.waitFor(() => expect(deposits).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
