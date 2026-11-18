import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { DEVELOPMENT, signedIn } from "../../test/session";
import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  it("holds the person's preferences", () => {
    render(<SettingsPage session={signedIn()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Your preferences" })).toBeVisible();
  });

  it("offers the person's own AI account only where the deployment does", () => {
    const { unmount } = render(<SettingsPage session={signedIn()} />);
    expect(screen.queryByRole("heading", { name: "Your AI account" })).toBeNull();
    unmount();
    render(<SettingsPage session={{ ...signedIn(), modelAccounts: true }} />);
    expect(screen.getByRole("heading", { name: "Your AI account" })).toBeVisible();
  });

  it("offers no AI account where nobody signs in", () => {
    render(<SettingsPage session={{ ...DEVELOPMENT, modelAccounts: true }} />);
    expect(screen.queryByRole("heading", { name: "Your AI account" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Your preferences" })).toBeVisible();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<SettingsPage session={signedIn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
