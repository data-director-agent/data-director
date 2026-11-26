import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("does not show a drafter's gap markers", () => {
    const readme = [
      "# Perovskite films",
      "",
      "## Licence",
      "",
      "_Licence not yet known._",
      "<!-- dd:gap q-1a2b -->",
      "",
      "Measured on the diffractometer <!-- dd:gap q-3c4d --> in 2025.",
      "",
    ].join("\n");
    const { container } = render(<Markdown>{readme}</Markdown>);
    expect(screen.getByText("Licence not yet known.")).toBeInTheDocument();
    expect(container).toHaveTextContent("Measured on the diffractometer in 2025.");
    expect(container.textContent).not.toContain("dd:gap");
    expect(container.textContent).not.toContain("<!--");
  });

  it("opens a link to another site in a new tab and says so", () => {
    const text = "See [the funder's policy](https://funder.example/policy) and https://doi.org/10.1/x.";
    render(<Markdown>{text}</Markdown>);
    const policy = screen.getByRole("link", { name: /the funder's policy/ });
    expect(policy).toHaveAttribute("href", "https://funder.example/policy");
    expect(policy).toHaveAttribute("target", "_blank");
    expect(policy).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(policy).toHaveAccessibleName(/^the funder's policy\s*\(opens in a new tab\)$/);
    // A bare address is linked in the same way.
    expect(screen.getByRole("link", { name: /doi\.org/ })).toHaveAttribute("target", "_blank");
  });

  it("leaves a link within the app, and an email address, in the same tab", () => {
    const text = "Open [the project](/projects/p1) or [ask us](mailto:data@uni.example).";
    render(<Markdown>{text}</Markdown>);
    for (const name of ["the project", "ask us"]) {
      expect(screen.getByRole("link", { name })).not.toHaveAttribute("target");
    }
  });

  it("never links a script address", () => {
    render(<Markdown>{"[click](javascript:alert(1))"}</Markdown>);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("shows other raw HTML as text, not rendered", () => {
    const { container } = render(<Markdown>{"Some <b>bold</b> text"}</Markdown>);
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent("Some <b>bold</b> text");
  });
});
