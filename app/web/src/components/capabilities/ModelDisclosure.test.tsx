import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelTag } from "./ModelDisclosure";

describe("ModelTag", () => {
  it("says an agent with no model is deterministic", () => {
    render(<ModelTag agent={{ models: [], modelsDeclared: true }} />);
    expect(screen.getByText("No AI model: deterministic")).toBeVisible();
  });

  it("says nothing is known when the card declares no models", () => {
    render(<ModelTag agent={{ models: [], modelsDeclared: false }} />);
    expect(screen.getByText("AI model not declared")).toBeVisible();
    expect(screen.queryByText(/deterministic/)).toBeNull();
  });

  it("names a remote model", () => {
    const models = [{ provider: "anthropic", model: "claude-test", hosting: "hosted" as const }];
    render(<ModelTag agent={{ models, modelsDeclared: true }} />);
    expect(screen.getByText(/Language model, remote:/)).toHaveTextContent("claude-test");
  });

  it("names a local model", () => {
    const models = [{ provider: "ollama", model: "llama-test", hosting: "local" as const }];
    render(<ModelTag agent={{ models, modelsDeclared: true }} />);
    expect(screen.getByText(/Language model, local:/)).toHaveTextContent("llama-test");
  });
});
