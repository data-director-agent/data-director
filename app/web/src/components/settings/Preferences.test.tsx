import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { Preferences } from "./Preferences";

const root = document.documentElement;

afterEach(() => {
  localStorage.clear();
  for (const name of [
    "data-theme",
    "data-motion",
    "data-text-size",
    "data-density",
  ]) {
    root.removeAttribute(name);
  }
});

describe("Preferences", () => {
  it("shows each preference as a group with the default chosen", async () => {
    const sections = [
      [
        "appearance",
        "Appearance",
        ["Colour scheme", "Text size", "Spacing", "Animation", "Your icon in the chat"],
        "Light",
      ],
      [
        "dates",
        "Dates and times",
        ["Date style", "Clock"],
        "As the date style writes it",
      ],
      [
        "starting",
        "Starting up",
        ["When you open Data Director"],
        "Return to the project you used last",
      ],
    ] as const;
    for (const [section, title, groups, checked] of sections) {
      const { container, unmount } = render(<Preferences section={section} />);
      expect(screen.getByRole("heading", { name: title })).toBeVisible();
      for (const group of groups) {
        expect(screen.getByRole("group", { name: group })).toBeVisible();
      }
      expect(screen.getByRole("radio", { name: checked })).toBeChecked();
      expect(await axe(container)).toHaveNoViolations();
      unmount();
    }
  });

  it("applies and remembers a choice at once", async () => {
    render(<Preferences section="appearance" />);
    await userEvent.click(screen.getByRole("radio", { name: "Larger" }));
    expect(screen.getByRole("radio", { name: "Larger" })).toBeChecked();
    expect(root.dataset.textSize).toBe("larger");
    expect(localStorage.getItem("dd-text-size")).toBe("larger");

    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(root.dataset.theme).toBe("dark");
  });

  it("lets the person choose the icon that stands for them in the chat", async () => {
    render(<Preferences section="appearance" />);
    expect(screen.getByRole("radio", { name: /Person/ })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: /Owl/ }));
    expect(screen.getByRole("radio", { name: /Owl/ })).toBeChecked();
    expect(localStorage.getItem("dd-person-icon")).toBe("owl");
  });

  it("shows an example of the chosen date style and clock", async () => {
    const { container } = render(<Preferences section="dates" />);
    await userEvent.click(screen.getByRole("radio", { name: /^British/ }));
    await userEvent.click(screen.getByRole("radio", { name: "24-hour" }));
    expect(container.querySelector(".preferences time")).toHaveTextContent(
      "14:05",
    );
    await userEvent.click(screen.getByRole("radio", { name: "12-hour" }));
    expect(container.querySelector(".preferences time")).toHaveTextContent(
      /pm/i,
    );
  });
});
