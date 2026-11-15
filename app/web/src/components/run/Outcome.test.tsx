import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import several from "../../../fixtures/agents-several.json";
import projectsFixture from "../../../fixtures/projects.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import type { ProjectSummary } from "../../project/api";
import { projectName } from "../../project/name";
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

  it("names the declared model a call was routed from, and only then", () => {
    const routed: ModelCall = {
      ...call("own"),
      model_provider: "openai",
      model_id: "gpt-test",
      model_declared: "claude-test",
    };
    const { list } = calls(routed, call("own"));
    if (!list) throw new Error("no list of calls");
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent(/gpt-test in place of claude-test, paid for by/);
    expect(second).not.toHaveTextContent(/in place of/);
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

describe("Outcome, the project a run is part of", () => {
  const project = (projectsFixture as ProjectSummary[])[0] as ProjectSummary;

  function review(of?: ProjectSummary | null) {
    const { container } = render(
      <Outcome result={{ envelope: shortlistRun(), checks }} agent={agent} idPrefix="run" project={of} />,
    );
    const callout = screen.getByText("Human review", { selector: ".not-built strong" }).closest(".not-built");
    if (!(callout instanceof HTMLElement)) throw new Error("no human review callout");
    return { container, callout };
  }

  it("names and links the project of the conversation that started the run", async () => {
    const { container, callout } = review(project);
    const link = within(callout).getByRole("link", { name: projectName(project) });
    expect(link).toHaveAttribute("href", `/projects/${encodeURIComponent(project.project_id)}`);
    expect(callout).not.toHaveTextContent(/not part of a project/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says a run is not part of a project when its conversation has none", () => {
    const { callout } = review(null);
    expect(callout).toHaveTextContent(/not part of a project/);
    expect(within(callout).queryByRole("link", { name: projectName(project) })).toBeNull();
  });

  it("makes no claim about a project it does not know", () => {
    const { callout } = review();
    expect(callout).not.toHaveTextContent(/part of/);
    expect(within(callout).queryByRole("link", { name: projectName(project) })).toBeNull();
  });
});
