import { render, screen } from "@testing-library/react";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("names how the value was derived", () => {
    render(<Badge derivation={{ path: "x", how: "model" }} record={{}} />);
    expect(screen.getByText("Language model")).toHaveAttribute(
      "title",
      "Written by a language model",
    );
  });

  it("prefers what the record says about itself", () => {
    render(
      <Badge
        derivation={{ path: "x", how: "model", recordedIn: "source" }}
        record={{ source: "registry" }}
      />,
    );
    expect(screen.getByText("Registry")).toBeInTheDocument();
  });

  it("falls back to the derivation when the record does not say", () => {
    render(<Badge derivation={{ path: "x", how: "lexical", recordedIn: "source" }} record={{}} />);
    expect(screen.getByText("Keyword rules")).toBeInTheDocument();
  });

  it("shows a value outside the vocabulary as given", () => {
    render(
      <Badge
        derivation={{ path: "x", how: "template", recordedIn: "source" }}
        record={{ source: "magic" }}
      />,
    );
    expect(screen.getByText("magic")).toHaveAttribute("title", "magic");
  });
});
