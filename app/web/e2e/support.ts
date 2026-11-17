/**
 * What the browser tests share: the shell's API answered from the fixtures app/tests/test_app.py
 * keeps current, axe, and reflow.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import several from "../fixtures/agents-several.json" with { type: "json" };
import conversation from "../fixtures/conversation.json" with { type: "json" };
import turn from "../fixtures/conversation-turn.json" with { type: "json" };
import flow from "../fixtures/process-flow.json" with { type: "json" };
import abstained from "../fixtures/run-abstained.json" with { type: "json" };
import succeeded from "../fixtures/run-succeeded.json" with { type: "json" };

function row(run: typeof succeeded | typeof abstained) {
  const { envelope } = run;
  return {
    invocation_id: envelope.invocation_id,
    agent_id: envelope.agent_id,
    status: envelope.outcome.status,
    completed_at: envelope.completed_at,
    acting_for: envelope.acting_for.name,
  };
}

/** Answer the shell's API from the fixtures: the agents, the phases and a run. */
export async function serve(page: Page, body: unknown, run: unknown = succeeded) {
  await page.route("/api/agents", (route) => route.fulfill({ json: body }));
  await page.route("/api/process-flow", (route) => route.fulfill({ json: flow }));
  await page.route("/api/runs", (route) =>
    route.fulfill({ json: route.request().method() === "POST" ? run : [row(succeeded)] }),
  );
  await page.route("/api/runs/*", (route) => route.fulfill({ json: succeeded }));
}

/** Who is signed in. Unless a test says otherwise, a development server: nobody signs in. */
export async function serveSession(page: Page, session: unknown) {
  await page.route("/api/session", (route) => route.fulfill({ json: session }));
}

/** The several-agents set plus an orchestrator, named by the profile (docs/specs/app.md). */
export const withOrchestrator = {
  ...several,
  profile: { ...several.profile, orchestrator: "orchestrator.stub" },
  agents: [
    ...several.agents,
    { ...several.agents[0], agent_id: "orchestrator.stub", grounding_mode: "delegation" },
  ],
};

export async function serveConversation(page: Page) {
  await serve(page, withOrchestrator);
  await page.route("/api/conversations", (route) =>
    route.fulfill(
      route.request().method() === "POST"
        ? { status: 201, json: { conversation_id: conversation.conversation_id } }
        : { json: [] },
    ),
  );
  await page.route("/api/conversations/*/turns", (route) =>
    route.fulfill({ status: 201, json: turn }),
  );
  await page.route("/api/conversations/*", (route) => route.fulfill({ json: conversation }));
}

export async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations;
}

export async function overflow(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}
