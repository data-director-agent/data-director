import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { Frame } from "./Frame";

describe("Frame", () => {
  it("marks the current page in the main navigation, and only that one", async () => {
    const { container } = render(
      <Frame current="/agents">
        <p>Content</p>
      </Frame>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Agents" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Conversation" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("holds the same things in the banner on every page", () => {
    const banners = ["/", "/agents"].map((current) => {
      const { unmount } = render(
        <Frame current={current}>
          <p>Content</p>
        </Frame>,
      );
      const text = screen.getByRole("banner").textContent;
      unmount();
      return text;
    });
    expect(banners[0]).toBe(banners[1]);
  });
});
