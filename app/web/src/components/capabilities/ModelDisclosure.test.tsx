import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import held from "../../../fixtures/model-account.json";
import none from "../../../fixtures/model-account-none.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import {
  type ModelAccountApi,
  ModelAccountApiContext,
  type RawModelAccount,
  fromRaw,
} from "../../model-account/api";
import { CapabilitiesPanel } from "./CapabilitiesPanel";
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

describe("CapabilitiesPanel, the person's own AI account", () => {
  const HELD = fromRaw(held as RawModelAccount);
  const NONE = fromRaw(none as RawModelAccount);
  const MODELS = [{ provider: "anthropic", model: "claude-test", hosting: "hosted" as const }];
  const [first] = normalise(several as unknown as RawAgentsResponse).agents;
  if (!first) throw new Error("no agent in the fixture");
  const modelBacked = first;

  function renderWith(read: ModelAccountApi["read"], ownAccounts: boolean, models = MODELS) {
    const api: ModelAccountApi = {
      read,
      enrol: () => Promise.reject(new Error("not here")),
      remove: () => Promise.reject(new Error("not here")),
    };
    return render(
      <ModelAccountApiContext.Provider value={api}>
        <CapabilitiesPanel agent={{ ...modelBacked, models }} ownAccounts={ownAccounts} />
      </ModelAccountApiContext.Provider>,
    );
  }

  it("shows the signed-in person the label of their own account", async () => {
    const { container } = renderWith(() => Promise.resolve(HELD), true);
    expect(await screen.findByText(held.account.label, { exact: false })).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("points a person with no account to their Profile page", async () => {
    renderWith(() => Promise.resolve(NONE), true);
    expect(await screen.findByRole("link", { name: "Profile page" })).toHaveAttribute(
      "href",
      "/profile",
    );
  });

  it("reads nothing when the deployment does not offer own accounts", () => {
    const read = vi.fn(() => Promise.resolve(HELD));
    renderWith(read, false);
    expect(read).not.toHaveBeenCalled();
  });

  it("reads nothing for an agent that calls no model", () => {
    const read = vi.fn(() => Promise.resolve(HELD));
    renderWith(read, true, []);
    expect(read).not.toHaveBeenCalled();
  });
});
