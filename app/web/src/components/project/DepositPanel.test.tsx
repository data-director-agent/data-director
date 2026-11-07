import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import refusedFixture from "../../../fixtures/project-validation-refused.json";
import validFixture from "../../../fixtures/project-validation.json";
import {
  type BuiltPackage,
  PackageRefused,
  type ProjectApi,
  ProjectApiContext,
  type Validation,
  httpProjectApi,
} from "../../project/api";
import { DepositPanel } from "./DepositPanel";

// What the server says (app/tests/test_deposit_routes.py): a project valid for ORDA, with the
// warnings of what ORDA recommends, and one with no approved metadata record.
const VALID = validFixture as Validation;
const REFUSED = refusedFixture as Validation;
const PROJECT = VALID.project_id;
const BUILT: BuiltPackage = {
  digest: "a".repeat(64),
  size: 20480,
  media_type: "application/zip",
  validation: VALID,
};

function renderPanel(api: Partial<ProjectApi>) {
  return render(
    <ProjectApiContext.Provider value={{ ...httpProjectApi, ...api }}>
      <DepositPanel projectId={PROJECT} />
    </ProjectApiContext.Provider>,
  );
}

describe("DepositPanel", () => {
  it("checks the project, builds the package and offers it for download by its digest", async () => {
    const buildPackage = vi.fn(() => Promise.resolve(BUILT));
    const { container } = renderPanel({ validate: () => Promise.resolve(VALID), buildPackage });
    expect(screen.queryByRole("button", { name: "Build the package" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Check the project" }));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(
      `The project is ready to deposit, with ${VALID.warnings.length} warnings.`,
    );
    const recommended = screen.getByRole("heading", { name: "What the repository recommends" });
    expect(recommended).toBeVisible();
    expect(screen.getByText(VALID.warnings[0]?.message ?? "")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Build the package" }));
    expect(buildPackage).toHaveBeenCalledWith(PROJECT);
    expect(status).toHaveTextContent("The deposit package is built (20.0 KB).");
    const download = screen.getByRole("link", { name: "Download the deposit package" });
    expect(download).toHaveAttribute("href", `/api/projects/${PROJECT}/packages/${BUILT.digest}`);
    expect(download).toHaveAttribute("download");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says what stops the package, in the harness's words, and offers no build", async () => {
    renderPanel({ validate: () => Promise.resolve(REFUSED) });
    await userEvent.click(screen.getByRole("button", { name: "Check the project" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "1 problem stops the package being built",
    );
    const stops = screen.getByRole("heading", { name: "What stops the package" });
    const list = stops.nextElementSibling as HTMLElement;
    expect(within(list).getByText(REFUSED.violations[0]?.message ?? "")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Build the package" })).not.toBeInTheDocument();
  });

  it("shows the validation a refused build came back with", async () => {
    renderPanel({
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.reject(new PackageRefused(REFUSED)),
    });
    await userEvent.click(screen.getByRole("button", { name: "Check the project" }));
    await userEvent.click(await screen.findByRole("button", { name: "Build the package" }));
    expect(await screen.findByRole("status")).toHaveTextContent("No package was built.");
    expect(screen.getByText(REFUSED.violations[0]?.message ?? "")).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Download the deposit package" }),
    ).not.toBeInTheDocument();
  });

  it("says when the server cannot be reached, and moves focus to it, with the keyboard alone", async () => {
    renderPanel({ validate: () => Promise.reject(new Error("the server answered 500")) });
    await userEvent.tab();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Check the project" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("the server answered 500");
    expect(alert).toHaveFocus();
  });
});
