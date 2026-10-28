import { render, screen } from "@testing-library/react";
import { Play } from "lucide-react";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("draws an icon that screen readers skip", () => {
    render(<Button icon={Play}>Run</Button>);
    const icon = screen.getByRole("button", { name: "Run" }).querySelector("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("draws no icon unless given one", () => {
    render(<Button>Run</Button>);
    expect(screen.getByRole("button").querySelector("svg")).toBeNull();
  });
});
