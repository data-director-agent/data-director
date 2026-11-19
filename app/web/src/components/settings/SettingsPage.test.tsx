import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { DEVELOPMENT, signedIn } from "../../test/session";
import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  it("holds the person's preferences, a section to a tab", async () => {
    render(<SettingsPage session={signedIn()} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Settings" }),
    ).toBeVisible();
    expect(screen.getByRole("tab", { name: "Appearance" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeVisible();
    for (const name of ["Dates and times", "Starting up"]) {
      await userEvent.click(screen.getByRole("tab", { name }));
      expect(screen.getByRole("heading", { name })).toBeVisible();
    }
    expect(screen.queryByRole("heading", { name: "Appearance" })).toBeNull();
  });

  it("offers the person's own AI account only where the deployment does", () => {
    const { unmount } = render(<SettingsPage session={signedIn()} />);
    expect(
      screen.queryByRole("heading", { name: "Your AI account" }),
    ).toBeNull();
    unmount();
    render(<SettingsPage session={{ ...signedIn(), modelAccounts: true }} />);
    expect(screen.getByRole("tab", { name: "AI account" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.getByRole("heading", { name: "Your AI account" }),
    ).toBeVisible();
  });

  it("offers no AI account where nobody signs in", () => {
    render(<SettingsPage session={{ ...DEVELOPMENT, modelAccounts: true }} />);
    expect(
      screen.queryByRole("heading", { name: "Your AI account" }),
    ).toBeNull();
    expect(screen.queryByRole("tab", { name: "AI account" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeVisible();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<SettingsPage session={signedIn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
