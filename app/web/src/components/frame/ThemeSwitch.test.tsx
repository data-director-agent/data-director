import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { ThemeSwitch } from "./ThemeSwitch";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("ThemeSwitch", () => {
  it("is off by default, so the scheme is light", async () => {
    const { container } = render(<ThemeSwitch />);
    expect(screen.getByRole("button", { name: "Dark mode" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("applies and remembers the dark scheme, and turns it off again", async () => {
    render(<ThemeSwitch />);
    const button = screen.getByRole("button", { name: "Dark mode" });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("dd-theme")).toBe("dark");

    await userEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("dd-theme")).toBe("light");
  });

  it("starts pressed when dark was chosen before", () => {
    localStorage.setItem("dd-theme", "dark");
    render(<ThemeSwitch />);
    expect(screen.getByRole("button", { name: "Dark mode" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
