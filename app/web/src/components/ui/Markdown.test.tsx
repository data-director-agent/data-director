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

  it("shows other raw HTML as text, not rendered", () => {
    const { container } = render(<Markdown>{"Some <b>bold</b> text"}</Markdown>);
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent("Some <b>bold</b> text");
  });
});
