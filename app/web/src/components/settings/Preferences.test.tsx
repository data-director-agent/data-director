import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { Preferences } from "./Preferences";

const root = document.documentElement;

afterEach(() => {
  localStorage.clear();
  for (const name of ["data-theme", "data-motion", "data-text-size", "data-density"]) {
    root.removeAttribute(name);
  }
});

describe("Preferences", () => {
  it("shows each preference as a group with the default chosen", async () => {
    const { container } = render(<Preferences />);
    expect(screen.getByRole("heading", { name: "Your preferences" })).toBeVisible();
    for (const group of ["Colour scheme", "Text size", "Spacing", "Animation", "Clock"]) {
      expect(screen.getByRole("group", { name: group })).toBeVisible();
    }
    expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Return to the project you used last" })).toBeChecked();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("applies and remembers a choice at once", async () => {
    render(<Preferences />);
    await userEvent.click(screen.getByRole("radio", { name: "Larger" }));
    expect(screen.getByRole("radio", { name: "Larger" })).toBeChecked();
    expect(root.dataset.textSize).toBe("larger");
    expect(localStorage.getItem("dd-text-size")).toBe("larger");

    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(root.dataset.theme).toBe("dark");
  });

  it("shows an example of the chosen date style and clock", async () => {
    const { container } = render(<Preferences />);
    await userEvent.click(screen.getByRole("radio", { name: /^British/ }));
    await userEvent.click(screen.getByRole("radio", { name: "24-hour" }));
    expect(container.querySelector(".preferences time")).toHaveTextContent("14:05");
    await userEvent.click(screen.getByRole("radio", { name: "12-hour" }));
    expect(container.querySelector(".preferences time")).toHaveTextContent(/pm/i);
  });
});
