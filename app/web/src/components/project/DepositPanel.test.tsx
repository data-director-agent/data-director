import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import builtFixture from "../../../fixtures/project-package.json";
import refusedFixture from "../../../fixtures/project-package-refused.json";
import chosenFixture from "../../../fixtures/repository-chosen.json";
import reviewFixture from "../../../fixtures/project-review.json";
import {
  type BuiltPackage,
  type DepositReview,
  PackageRefused,
  type ProjectApi,
  ProjectApiContext,
  type RepositoryRequirements,
  type Validation,
} from "../../project/api";
import type { Problem } from "../../run/types";
import { DepositPanel, outcome, sizeInWords } from "./DepositPanel";
import { DEPOSIT_GUIDE } from "./PackageBuilt";

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
// The same project once its inventory lists field notes (app/tests/test_deposit_package.py): valid,
// and waiting for the researcher to decide each marked file and confirm the checks before deposit.
const REVIEW = reviewFixture as DepositReview;
const PAUSED: Validation = { ...VALID, ready: false, review: REVIEW };
// ORDA as the server resolves it (app/tests/test_repository_choice.py): form labels, its address
// and what its profile leaves unconfirmed.
const ORDA = chosenFixture as RepositoryRequirements;

function renderPanel(api: Partial<ProjectApi>, revision = 0) {
  const full = {
    repository: () => Promise.resolve(null),
    ...api,
  } as ProjectApi;
  const panel = (n: number) => (
    <ProjectApiContext.Provider value={full}>
      <DepositPanel projectId={PROJECT_ID} revision={n} />
    </ProjectApiContext.Provider>
  );
  const rendered = render(panel(revision));
  return {
    ...rendered,
    setRevision: (n: number) => rendered.rerender(panel(n)),
  };
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
    expect(outcome({ ...VALID, warnings: [] })).toBe(
      "The project is ready to package.",
    );
  });
});

describe("DepositPanel", () => {
  it("has a live region from the start, before anything is checked", () => {
    renderPanel({});
    expect(within(region()).getByRole("status")).toBeEmptyDOMElement();
    expect(
      within(region()).queryByRole("button", { name: /Build/ }),
    ).not.toBeInTheDocument();
  });

  it("shows each violation and warning in the harness's words, and offers no build", async () => {
    const validate = vi.fn(() => Promise.resolve(INVALID));
    const user = userEvent.setup();
    const { container } = renderPanel({ validate });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );

    expect(validate).toHaveBeenCalledWith(PROJECT_ID);
    expect(await within(region()).findByRole("status")).toHaveTextContent(
      outcome(INVALID),
    );
    const violations = within(region()).getByRole("region", {
      name: /Must be fixed/,
    });
    for (const result of INVALID.violations) {
      expect(within(violations).getByText(result.message)).toBeVisible();
    }
    const warnings = within(region()).getByRole("region", {
      name: /Worth fixing/,
    });
    for (const result of INVALID.warnings) {
      expect(within(warnings).getByText(result.message)).toBeVisible();
    }
    expect(
      within(region()).queryByRole("button", { name: /Build/ }),
    ).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("builds the package of a valid project and offers it to download, by keyboard", async () => {
    const buildPackage = vi.fn(() => Promise.resolve(BUILT));
    const user = userEvent.setup();
    const { container } = renderPanel({
      validate: () => Promise.resolve(VALID),
      buildPackage,
    });

    await user.tab();
    expect(
      within(region()).getByRole("button", { name: "Check the project" }),
    ).toHaveFocus();
    await user.keyboard("{Enter}");
    const build = await within(region()).findByRole("button", {
      name: "Build the package",
    });
    expect(
      within(region()).queryByRole("region", { name: /Must be fixed/ }),
    ).not.toBeInTheDocument();
    await user.tab();
    expect(build).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(buildPackage).toHaveBeenCalledWith(PROJECT_ID);
    const link = await within(region()).findByRole("link", {
      name: /Download the package/,
    });
    expect(link).toHaveAttribute("href", BUILT.package.href);
    expect(link).toHaveAttribute("download", expect.stringMatching(/\.zip$/));
    expect(within(region()).getByText(BUILT.package.digest)).toBeVisible();
    expect(within(region()).getByRole("status")).toHaveTextContent(
      /package is built/,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says why no package was built when the harness refuses it", async () => {
    const user = userEvent.setup();
    renderPanel({
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.reject(new PackageRefused(REFUSED)),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    await user.click(
      await within(region()).findByRole("button", {
        name: "Build the package",
      }),
    );

    const refused = await within(region()).findByText(
      /not yet valid for deposit/,
    );
    expect(refused).toBeVisible();
    expect(refused.closest(".callout")).toHaveFocus();
    expect(within(region()).getByRole("status")).toHaveTextContent(
      /^No package was built/,
    );
    for (const result of INVALID.violations) {
      expect(within(region()).getByText(result.message)).toBeVisible();
    }
    expect(
      within(region()).queryByRole("link", { name: /Download/ }),
    ).not.toBeInTheDocument();
  });

  it("says what to do next for the chosen repository, from its requirements", async () => {
    const user = userEvent.setup();
    const { container } = renderPanel({
      repository: () => Promise.resolve(ORDA),
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.resolve(BUILT),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    const build = await within(region()).findByRole("button", {
      name: "Build the package",
    });
    await user.click(build);

    const next = await within(region()).findByRole("region", {
      name: "What to do next",
    });
    expect(within(region()).getByRole("status")).toHaveTextContent(
      /steps below/,
    );
    expect(within(next).getAllByRole("list")[0]?.tagName).toBe("OL");
    expect(
      within(next).getByRole("link", { name: ORDA.repository_name }),
    ).toHaveAttribute("href", ORDA.repository_url);
    const labels = (obligation: string) => [
      ...new Set(
        ORDA.fields
          .filter((f) => f.obligation === obligation && f.form_label)
          .map((f) => f.form_label),
      ),
    ];
    const required = within(next).getByRole("list", {
      name: "Fields the form requires",
    });
    expect(
      within(required)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(labels("required"));
    const recommended = within(next).getByRole("list", {
      name: "Fields worth filling",
    });
    expect(
      within(recommended)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(labels("recommended"));
    for (const field of ORDA.fields.filter((f) => !f.form_label)) {
      expect(within(next).getByText(field.property)).toBeVisible();
    }
    expect(ORDA.unconfirmed?.length).toBeGreaterThan(0);
    for (const item of ORDA.unconfirmed ?? []) {
      expect(within(next).getByText(item)).toBeVisible();
    }
    expect(
      within(next).getByRole("link", { name: /user guide/ }),
    ).toHaveAttribute("href", DEPOSIT_GUIDE);
    expect(
      within(region()).getByRole("heading", { name: "The package is built" }),
    ).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("gives general steps when no repository can be read", async () => {
    const user = userEvent.setup();
    renderPanel({
      repository: () => Promise.reject(new Error("unavailable")),
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.resolve(BUILT),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    await user.click(
      await within(region()).findByRole("button", {
        name: "Build the package",
      }),
    );

    const next = await within(region()).findByRole("region", {
      name: "What to do next",
    });
    expect(
      within(next).queryByRole("list", { name: /Fields/ }),
    ).not.toBeInTheDocument();
    expect(
      within(next).queryByText(/Not yet confirmed/),
    ).not.toBeInTheDocument();
    expect(
      within(next).getByRole("link", { name: /user guide/ }),
    ).toBeVisible();
  });

  it("drops a check that a later decision has overtaken", async () => {
    const user = userEvent.setup();
    const { setRevision } = renderPanel({
      validate: () => Promise.resolve(VALID),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    await within(region()).findByRole("button", { name: "Build the package" });

    setRevision(1);
    expect(
      within(region()).getByText(/changed since it was checked/),
    ).toBeVisible();
    expect(
      within(region()).queryByRole("button", { name: /Build/ }),
    ).not.toBeInTheDocument();
  });

  it("waits for a person to decide each marked file and confirm, and offers no build", async () => {
    const user = userEvent.setup();
    const decideItem = vi.fn(() => Promise.resolve(REVIEW));
    const validate = vi.fn(() => Promise.resolve(PAUSED));
    const { container } = renderPanel({ validate, decideItem });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );

    expect(await within(region()).findByRole("status")).toHaveTextContent(
      outcome(PAUSED),
    );
    expect(outcome(PAUSED)).not.toMatch(/ready to package/);
    expect(
      within(region()).queryByRole("button", { name: /Build/ }),
    ).not.toBeInTheDocument();
    const decide = within(region()).getByRole("region", {
      name: "Decide before packaging",
    });
    for (const item of REVIEW.items) {
      expect(within(decide).getAllByText(item.question).length).toBeGreaterThan(
        0,
      );
    }
    for (const text of REVIEW.not_checked) {
      expect(within(decide).getByText(text)).toBeVisible();
    }
    expect(await axe(container)).toHaveNoViolations();

    // A decision is recorded for the item, and the project is checked again.
    const first = REVIEW.items[0] as DepositReview["items"][number];
    const form = within(decide).getAllByRole("form")[0] as HTMLElement;
    await user.click(within(form).getByRole("radio", { name: /Leave it out/ }));
    await user.click(
      within(form).getByRole("button", { name: "Record my decision" }),
    );
    expect(decideItem).toHaveBeenCalledWith(
      PROJECT_ID,
      first.item_id,
      "leave_out",
      undefined,
    );
    expect(validate).toHaveBeenCalledTimes(2);
  });

  it("confirms the checks before deposit only once every statement is ticked", async () => {
    const user = userEvent.setup();
    const confirmChecks = vi.fn(() => Promise.resolve(REVIEW));
    renderPanel({
      validate: () =>
        Promise.resolve({ ...PAUSED, review: { ...REVIEW, items: [] } }),
      confirmChecks,
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    const confirm = await within(region()).findByRole("button", {
      name: "Confirm",
    });
    for (const statement of REVIEW.statements) {
      expect(confirm).toBeDisabled();
      await user.click(
        within(region()).getByRole("checkbox", { name: statement.text }),
      );
    }
    await user.click(confirm);
    expect(confirmChecks).toHaveBeenCalledWith(
      PROJECT_ID,
      REVIEW.statements.map((s) => s.id),
    );
  });

  it("says a build is running, and starts only one however often the button is pressed", async () => {
    let finish: (built: BuiltPackage) => void = () => undefined;
    const buildPackage = vi.fn(
      () => new Promise<BuiltPackage>((resolve) => (finish = resolve)),
    );
    const user = userEvent.setup();
    renderPanel({ validate: () => Promise.resolve(VALID), buildPackage });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    const build = await within(region()).findByRole("button", {
      name: "Build the package",
    });
    await user.click(build);

    const running = within(region()).getByRole("button", { name: /Build/ });
    expect(running).toHaveAttribute("aria-disabled", "true");
    expect(
      within(region()).getByRole("button", { name: "Check the project" }),
    ).toBeDisabled();
    expect(within(region()).getByRole("status")).not.toBeEmptyDOMElement();
    await user.click(running);
    expect(buildPackage).toHaveBeenCalledTimes(1);

    finish(BUILT);
    const built = await within(region()).findByRole("heading", {
      name: "The package is built",
    });
    // The heading takes focus in an effect after it renders, so wait for it.
    await waitFor(() => expect(built).toHaveFocus());
    expect(
      within(region()).queryByRole("button", { name: /Build/ }),
    ).not.toBeInTheDocument();
  });

  it("says when the package cannot be built, in an alert that takes focus", async () => {
    const user = userEvent.setup();
    const { container } = renderPanel({
      validate: () => Promise.resolve(VALID),
      buildPackage: () => Promise.reject(new Error("the server answered 500")),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    await user.click(
      await within(region()).findByRole("button", {
        name: "Build the package",
      }),
    );

    const alert = await within(region()).findByRole("alert");
    expect(alert).toHaveTextContent("the server answered 500");
    expect(alert).toHaveFocus();
    expect(
      within(region()).queryByRole("link", { name: /Download/ }),
    ).not.toBeInTheDocument();
    // The check still stands, so the build can be tried again.
    expect(
      within(region()).getByRole("button", { name: "Build the package" }),
    ).toBeEnabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when the project cannot be checked", async () => {
    const user = userEvent.setup();
    renderPanel({
      validate: () => Promise.reject(new Error("the server answered 500")),
    });
    await user.click(
      within(region()).getByRole("button", { name: "Check the project" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the server answered 500",
    );
  });
});
