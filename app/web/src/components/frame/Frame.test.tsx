import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { type FeedbackApi, FeedbackApiContext } from "../../feedback/api";
import { about } from "../../test/api";
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
    expect(
      within(nav).getByRole("link", { name: "Conversation" }),
    ).not.toHaveAttribute("aria-current");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("holds one polite and one assertive live region from the start", () => {
    render(
      <Frame current="/agents">
        <p>Content</p>
      </Frame>,
    );
    expect(screen.getByRole("log", { name: "Announcements" })).toHaveAttribute(
      "aria-live",
      "polite",
    );
    expect(screen.getByRole("log", { name: "Errors" })).toHaveAttribute(
      "aria-live",
      "assertive",
    );
  });

  it("links the app name in the banner to the home page", () => {
    render(
      <Frame current="/agents">
        <p>Content</p>
      </Frame>,
    );
    expect(screen.getByRole("link", { name: "Data Director" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("puts Project first in the main navigation, before the conversation", () => {
    render(
      <Frame current="/project">
        <p>Content</p>
      </Frame>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    const names = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    // The order of the rest may change as pages are added; Project leads and the conversation
    // follows it.
    expect(names[0]).toBe("Project");
    expect(names.indexOf("Conversation")).toBeGreaterThan(0);
    // `/project` opens the current project's page (`ProjectLanding`), not the list of projects.
    const projects = within(nav).getByRole("link", { name: "Project" });
    expect(projects).toHaveAttribute("href", "/project");
    expect(projects).toHaveAttribute("aria-current", "page");
  });

  it("has the journey map in the main navigation, straight after Project", () => {
    render(
      <Frame current="/journey">
        <p>Content</p>
      </Frame>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    const names = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names.indexOf("Journey map")).toBe(names.indexOf("Project") + 1);
    const link = within(nav).getByRole("link", { name: "Journey map" });
    expect(link).toHaveAttribute("href", "/journey");
    expect(link).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "Project" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("has the activity log as a page of its own in the main navigation", () => {
    render(
      <Frame current="/activity">
        <p>Content</p>
      </Frame>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    const link = within(nav).getByRole("link", { name: "Activity log" });
    expect(link).toHaveAttribute("href", "/activity");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("links to the settings from the banner, marked current on that page", () => {
    const { unmount } = render(
      <Frame current="/">
        <p>Content</p>
      </Frame>,
    );
    const banner = screen.getByRole("banner");
    const link = within(banner).getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "/settings");
    expect(link).not.toHaveAttribute("aria-current");
    unmount();
    render(
      <Frame current="/settings">
        <p>Content</p>
      </Frame>,
    );
    expect(
      within(screen.getByRole("banner")).getByRole("link", { name: "Settings" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("links to the user guide in a new tab", () => {
    render(
      <Frame current="/">
        <p>Content</p>
      </Frame>,
    );
    expect(screen.getByRole("link", { name: /^User guide/ })).toHaveAttribute(
      "href",
      "https://data-director-agent.github.io/data-director/user-guide/",
    );
    expect(screen.getByRole("link", { name: /^User guide/ })).toHaveAttribute(
      "target",
      "_blank",
    );
  });

  it("draws an icon beside each banner link, hidden from screen readers", () => {
    render(
      <Frame current="/">
        <p>Content</p>
      </Frame>,
    );
    const banner = screen.getByRole("banner");
    for (const name of [
      "Project",
      "Conversation",
      "Activity log",
      "Agents",
      "User guide",
      "Report a problem",
      "Settings",
    ]) {
      // An external link's name goes on to say it opens in a new tab.
      const control = within(banner).getByRole("link", { name: new RegExp(`^${name}`) });
      const icon = control.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
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

  it("credits the University of Sheffield and the RDA in the footer", async () => {
    const { container } = render(
      <Frame current="/">
        <p>Content</p>
      </Frame>,
    );
    const footer = screen.getByRole("contentinfo");
    expect(
      within(footer).getByRole("link", {
        name: /^The University of Sheffield/,
      }),
    ).toHaveAttribute("href", "https://www.sheffield.ac.uk/");
    expect(
      within(footer).getByRole("link", { name: /^Research Data Alliance/ }),
    ).toHaveAttribute("href", "https://www.rd-alliance.org/");
    expect(
      within(footer).getByRole("link", {
        name: /Data Director Agentic AI Blueprint/,
      }),
    ).toHaveAttribute("href", "https://doi.org/10.15497/RDA00157");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("links the project's pages in a footer navigation", async () => {
    const { container } = render(
      <Frame current="/">
        <p>Content</p>
      </Frame>,
    );
    const nav = within(screen.getByRole("contentinfo")).getByRole(
      "navigation",
      {
        name: "Footer",
      },
    );
    const site = "https://data-director-agent.github.io/data-director/";
    expect(within(nav).getByRole("link", { name: /^About/ })).toHaveAttribute(
      "href",
      site,
    );
    expect(
      within(nav).getByRole("link", { name: /^Project privacy notice/ }),
    ).toHaveAttribute("href", `${site}privacy/`);
    expect(
      within(nav).getByRole("link", { name: /^Contribute/ }),
    ).toHaveAttribute(
      "href",
      "https://github.com/data-director-agent/data-director/blob/main/CONTRIBUTING.md",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("names the deployed commit in the footer", async () => {
    const api = withAbout(() =>
      Promise.resolve(
        about({ commit: "abcdef0123456789", privacy_notice_url: null }),
      ),
    );
    const { container } = render(
      <FeedbackApiContext.Provider value={api}>
        <Frame current="/">
          <p>Content</p>
        </Frame>
      </FeedbackApiContext.Provider>,
    );
    const footer = screen.getByRole("contentinfo");
    expect(
      await within(footer).findByText("v0.3.0 (abcdef0)"),
    ).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("links the operator's privacy notice in the footer when there is one", async () => {
    const api = withAbout(() =>
      Promise.resolve(
        about({ commit: "abcdef0123456789", privacy_notice_url: "https://example.ac.uk/data-director/privacy" }),
      ),
    );
    const { container } = render(
      <FeedbackApiContext.Provider value={api}>
        <Frame current="/">
          <p>Content</p>
        </Frame>
      </FeedbackApiContext.Provider>,
    );
    const footer = screen.getByRole("contentinfo");
    expect(
      await within(footer).findByRole("link", { name: /^Privacy notice/ }),
    ).toHaveAttribute("href", "https://example.ac.uk/data-director/privacy");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows no privacy link when the operator has set no notice", async () => {
    const api = withAbout(() =>
      Promise.resolve(
        about({ commit: "abcdef0123456789", privacy_notice_url: null }),
      ),
    );
    render(
      <FeedbackApiContext.Provider value={api}>
        <Frame current="/">
          <p>Content</p>
        </Frame>
      </FeedbackApiContext.Provider>,
    );
    const footer = screen.getByRole("contentinfo");
    // The build line arrives with the same answer, so once it is there the link would be too.
    expect(
      await within(footer).findByText("v0.3.0 (abcdef0)"),
    ).toBeInTheDocument();
    expect(
      within(footer).queryByRole("link", { name: /^Privacy notice/ }),
    ).not.toBeInTheDocument();
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
