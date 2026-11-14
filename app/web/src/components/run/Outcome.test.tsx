import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import type { ModelCall } from "../../run/types";
import { shortlistRun } from "../../test/shortlist";
import { Outcome } from "./Outcome";

const [first] = normalise(several as unknown as RawAgentsResponse).agents;
if (!first) throw new Error("no agent in the fixture");
const agent = first;
const checks = { grounding: null, sources: null };

function call(model_account?: ModelCall["model_account"]): ModelCall {
  return {
    model_provider: "anthropic",
    model_id: "claude-test",
    called_at: "2026-11-13T12:00:00Z",
    prompt_digest: "e".repeat(64),
    ...(model_account ? { model_account } : {}),
  };
}

function calls(...made: ModelCall[]) {
  const envelope = shortlistRun({ telemetry: { model_calls: made } });
  const { container } = render(
    <Outcome result={{ envelope, checks }} agent={agent} idPrefix="run" />,
  );
  const facts = screen.getByText("About this run").closest("details");
  if (!facts) throw new Error("no facts about the run");
  return { container, list: within(facts).queryByRole("list") };
}

describe("Outcome, model calls", () => {
  it("says whose account paid for each call, own or the deployment's", async () => {
    const { container, list } = calls(call("own"), call("deployment"));
    if (!list) throw new Error("no list of calls");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(/own AI account/);
    expect(items[1]).toHaveTextContent(/deployment's AI account/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when a run recorded no payer", () => {
    const { list } = calls(call());
    if (!list) throw new Error("no list of calls");
    expect(within(list).getByRole("listitem")).toHaveTextContent(/did not record/);
  });

  it("lists no calls for a run that made none", () => {
    expect(calls().list).toBeNull();
  });
});
