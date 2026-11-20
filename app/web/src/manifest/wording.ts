/**
 * Plain-language wording for the contract's vocabulary.
 *
 * Kept in step with the LinkML descriptions in sdk/src/dd_sdk/schema/data_director.yaml and
 * with the linter's rules (harness/src/dd_harness/grounding.py). The wording states what the
 * harness checks and no more: a grounding check is a consistency check, not proof that an
 * agent retrieved anything (docs/specs/grounding.md).
 */

import type { StepState } from "../run/reduce";
import type { OutcomeStatus } from "../run/types";

export { className, fieldName } from "@data-director/agent-view";

/** Model providers by the name a manifest gives them. One not listed is shown as given. */
export const PROVIDER: Record<string, string> = {
  anthropic: "Anthropic",
};

/** How a model is run, from the card's `hosting`: where the input goes when the agent uses it. */
export const HOSTING: Record<"hosted" | "local", { label: string; explanation: string }> = {
  hosted: { label: "Remote", explanation: "runs on its provider's service, outside this institution" },
  local: { label: "Local", explanation: "runs on this institution's own infrastructure" },
};

/** Each outcome status: a heading word and the status class it is shown with. */
export const OUTCOME: Record<
  OutcomeStatus,
  { label: string; tone: "ok" | "warn" | "danger" | "undeclared" }
> = {
  succeeded: { label: "Succeeded", tone: "ok" },
  abstained: { label: "Abstained", tone: "warn" },
  referred: { label: "Referred to a person", tone: "warn" },
  failed: { label: "Failed", tone: "danger" },
  suspended: { label: "Suspended", tone: "undeclared" },
};

/**
 * Each reason code (`ReasonCode` in data_director.yaml): what it means, and what the person can
 * do next. An abstention is an answer, not an error.
 */
export const REASON: Record<string, { meaning: string; next: string }> = {
  no_qualifying_resource: {
    meaning: "It found candidates, but none was a close enough match to recommend.",
    next: "Add more specific keywords, themes or fields, or ask a data steward.",
  },
  no_candidates_retrieved: {
    meaning: "It searched the registry and found nothing.",
    next: "Try broader keywords or themes.",
  },
  registry_unavailable: {
    meaning: "It could not search the registry. This is not the same as finding nothing.",
    next: "Try again later.",
  },
  not_applicable: {
    meaning: "The question does not apply to this input.",
    next: "Check that you chose the right agent for this input.",
  },
  insufficient_input: {
    meaning: "The input does not give it enough to work with.",
    next: "Add a title, keywords, themes or media types, then run it again.",
  },
  capability_not_implemented: {
    meaning: "This agent does not do this yet. It says so rather than pretending to.",
    next: "Ask a data steward, or use another agent.",
  },
  requires_human_judgement: {
    meaning: "The agent judged that a person should decide this.",
    next: "Give the run id to a data steward.",
  },
  policy_requires_approval: {
    meaning: "This deployment's policy says runs of this agent need a data steward's approval.",
    next: "Give the run id to a data steward. Approving runs is not built yet (#16).",
  },
  outside_agent_scope: {
    meaning: "The request asks for something this agent does not do.",
    next: "Use another agent.",
  },
  model_account_missing: {
    meaning: "This deployment needs your own AI account for this agent, and none is added.",
    next: "Add your AI account on your Settings page, then run it again.",
  },
  model_account_rejected: {
    meaning: "Your AI provider refused your account's key.",
    next: "Check the key with your provider, replace it on your Settings page, then run it again.",
  },
  model_account_limit: {
    meaning: "Your AI provider reported a usage or rate limit on your account.",
    next: "Wait and run it again, or raise the limit with your provider.",
  },
};

/** Whose account paid for a model call (`ModelCall.model_account`), never whose. */
export const MODEL_ACCOUNT: Record<"own" | "deployment", string> = {
  own: "the own AI account of the person it acted for",
  deployment: "this deployment's AI account",
};

/** A stage's state as the run view draws it: the reducer's, with a check's finish told as passed
 * or failed by its report. */
export type StageState = StepState | "passed" | "failed";

export const STAGE_STATE: Record<
  StageState,
  { label: string; tone: "ok" | "warn" | "danger" | "undeclared" | "plain" }
> = {
  waiting: { label: "Waiting", tone: "plain" },
  running: { label: "Running", tone: "plain" },
  passed: { label: "Passed", tone: "ok" },
  failed: { label: "Failed", tone: "danger" },
  stopped: { label: "Stopped", tone: "warn" },
  finished: { label: "Done", tone: "ok" },
  "not-reached": { label: "Not reached", tone: "plain" },
};

/** What the run view says of the agent's activity while its stage runs (`AgentActivity`). */
export const AGENT_ACTIVITY = {
  subagent: { running: "Asking", done: "Asked", failed: "Could not ask" },
  tool: { running: "Using", done: "Used", failed: "Could not use" },
  /** Said once the stream has been quiet for a while; it claims nothing it does not know. */
  quiet: "Still working: some questions take a minute or two.",
  earlier: (n: number) => `and ${n} earlier`,
} as const;
