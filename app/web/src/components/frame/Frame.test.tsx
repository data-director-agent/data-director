import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { type FeedbackApi, FeedbackApiContext } from "../../feedback/api";
import { Frame } from "./Frame";

function withAbout(about: FeedbackApi["about"]) {
  return { about, send: () => Promise.reject(new Error("unused")) };
}

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

  it("names the deployed commit in the footer", async () => {
    const api = withAbout(() =>
      Promise.resolve({
        app_version: "0.3.0",
        harness_version: "0.1.0",
        commit: "abcdef0123456789",
        feedback_enabled: false,
      }),
    );
    const { container } = render(
      <FeedbackApiContext.Provider value={api}>
        <Frame current="/">
          <p>Content</p>
        </Frame>
      </FeedbackApiContext.Provider>,
    );
    const footer = screen.getByRole("contentinfo");
    expect(await within(footer).findByText("v0.3.0 (abcdef0)")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("leaves the footer empty when the build cannot be read", async () => {
    const api = withAbout(() => Promise.reject(new Error("down")));
    render(
      <FeedbackApiContext.Provider value={api}>
        <Frame current="/">
          <p>Content</p>
        </Frame>
      </FeedbackApiContext.Provider>,
    );
    await Promise.resolve();
    expect(screen.getByRole("contentinfo")).toBeVisible();
    expect(screen.getByRole("contentinfo")).not.toHaveTextContent("Build");
  });
});
