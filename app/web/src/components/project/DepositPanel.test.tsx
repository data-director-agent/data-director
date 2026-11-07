import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import builtFixture from "../../../fixtures/project-package.json";
import refusedFixture from "../../../fixtures/project-package-refused.json";
import {
  type BuiltPackage,
  PackageRefused,
  type ProjectApi,
  ProjectApiContext,
  type Validation,
} from "../../project/api";
import type { Problem } from "../../run/types";
import { DepositPanel, outcome, sizeInWords } from "./DepositPanel";

// What the server says (app/tests/test_deposit_package.py): a project with Zenodo chosen and no metadata
// record approved, refused with one violation and a warning; and, once one is approved, the
// package built, with warnings only.
const REFUSED = refusedFixture as Problem & { validation: Validation };
const INVALID = REFUSED.validation;
const BUILT = builtFixture as BuiltPackage;
// The validation alone, as `POST /validation` answers for the same project.
const VALID: Validation = Object.fromEntries(
  Object.entries(BUILT).filter(([key]) => key !== "package"),
) as unknown as Validation;
const PROJECT_ID = BUILT.project_id;

function renderPanel(api: Partial<ProjectApi>, revision = 0) {
  const full = { ...api } as ProjectApi;
  const panel = (n: number) => (
    <ProjectApiContext.Provider value={full}>
      <DepositPanel projectId={PROJECT_ID} revision={n} />
    </ProjectApiContext.Provider>
  );
  const rendered = render(panel(revision));
  return { ...rendered, setRevision: (n: number) => rendered.rerender(panel(n)) };
}

function region() {
  return screen.getByRole("region", { name: "Deposit package" });
}

describe("sizeInWords", () => {
  it("says bytes, kilobytes and megabytes", () => {
    expect(sizeInWords(1)).toBe("1 byte");
    expect(sizeInWords(900)).toBe("900 bytes");
    expect(sizeInWords(1536)).toBe("1.5 KB");
    expect(sizeInWords(3 * 1024 * 1024)).toBe("3 MB");
  });
});

describe("outcome", () => {
  it("says whether the project is ready, and how many problems or warnings it has", () => {
    expect(outcome(INVALID)).toMatch(/^1 problem must be fixed/);
    expect(outcome(VALID)).toMatch(/ready to package, with \d+ warnings/);
    expect(outcome({ ...VALID, warnings: [] })).toBe("The project is ready to package.");
  });
});

describe("DepositPanel", () => {
  it("has a live region from the start, before anything is checked", () => {
    renderPanel({});
    expect(within(region()).getByRole("status")).toBeEmptyDOMElement();
    expect(within(region()).queryByRole("button", { name: /Build/ })).not.toBeInTheDocument();
  });

  it("shows each violation and warning in the harness's words, and offers no build", async () => {
    const validate = vi.fn(() => Promise.resolve(INVALID));
    const user = userEvent.setup();
    const { container } = renderPanel({ validate });
    await user.click(within(region()).getByRole("button", { name: "Check the project" }));

    expect(validate).toHaveBeenCalledWith(PROJECT_ID);
    expect(await within(region()).findByRole("status")).toHaveTextContent(outcome(INVALID));
    const violations = within(region()).getByRole("region", { name: /Must be fixed/ });
    for (const result of INVALID.violations) {
      expect(within(violations).getByText(result.message)).toBeVisible();
    }
    const warnings = within(region()).getByRole("region", { name: /Worth fixing/ });
    for (const result of INVALID.warnings) {
      expect(within(warnings).getByText(result.message)).toBeVisible();
    }
    expect(within(region()).queryByRole("button", { name: /Build/ })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("builds the package of a valid project and offers it to download, by keyboard", async () => {
    const buildPackage = vi.fn(() => Promise.resolve(BUILT));
    const user = userEvent.setup();
    const { container } = renderPanel({ validate: () => Promise.resolve(VALID), buildPackage });

    await user.tab();
    expect(within(region()).getByRole("button", { name: "Check the project" })).toHaveFocus();
    await user.keyboard("{Enter}");
    const build = await within(region()).findByRole("button", { name: "Build the package" });
    expect(within(region()).queryByRole("region", { name: /Must be fixed/ })).not.toBeInTheDocument();
    await user.tab();
    expect(build).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(buildPackage).toHaveBeenCalledWith(PROJECT_ID);
    const link = await within(region()).findByRole("link", { name: /Download the package/ });
    expect(link).toHaveAttribute("href", BUILT.package.href);
    expect(link).toHaveAttribute("download", expect.stringMatching(/\.zip$/));
    expect(within(region()).getByText(BUILT.package.digest)).toBeVisible();
    expect(within(region()).getByRole("status")).toHaveTextContent(/package is built/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says why no package was built when the harness refuses it", async () => {
    const user = userEvent.setup();
    renderPanel({
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.reject(new PackageRefused(REFUSED)),
    });
    await user.click(within(region()).getByRole("button", { name: "Check the project" }));
    await user.click(await within(region()).findByRole("button", { name: "Build the package" }));

    expect(await within(region()).findByText(/not yet valid for deposit/)).toBeVisible();
    expect(within(region()).getByRole("status")).toHaveTextContent(/^No package was built/);
    for (const result of INVALID.violations) {
      expect(within(region()).getByText(result.message)).toBeVisible();
    }
    expect(within(region()).queryByRole("link", { name: /Download/ })).not.toBeInTheDocument();
  });

  it("drops a check that a later decision has overtaken", async () => {
    const user = userEvent.setup();
    const { setRevision } = renderPanel({ validate: () => Promise.resolve(VALID) });
    await user.click(within(region()).getByRole("button", { name: "Check the project" }));
    await within(region()).findByRole("button", { name: "Build the package" });

    setRevision(1);
    expect(within(region()).getByText(/changed since it was checked/)).toBeVisible();
    expect(within(region()).queryByRole("button", { name: /Build/ })).not.toBeInTheDocument();
  });

  it("says when the project cannot be checked", async () => {
    const user = userEvent.setup();
    renderPanel({ validate: () => Promise.reject(new Error("the server answered 500")) });
    await user.click(within(region()).getByRole("button", { name: "Check the project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("the server answered 500");
  });
});
