/**
 * Plain-language wording for the contract's vocabulary.
 *
 * Kept in step with the LinkML descriptions in sdk/src/dd_sdk/schema/data_director.yaml and
 * with the linter's rules (harness/src/dd_harness/grounding.py). The wording states what the
 * harness checks and no more: a grounding check is a consistency check, not proof that an
 * agent retrieved anything (ADR-0016).
 */

import type { StageState } from "../run/stages";
import type { OutcomeStatus } from "../run/types";
import type { DerivationHow, GroundingMode } from "./types";

export const GROUNDING: Record<GroundingMode, { label: string; explanation: string }> = {
  retrieval: {
    label: "Cites records it retrieved",
    explanation:
      "Each result names the records it relies on. Data Director checks that the citations " +
      "are consistent with the records the agent reports retrieving, and re-checks each cited " +
      "record against a pinned copy. This does not prove the agent retrieved them.",
  },
  input_only: {
    label: "Relies only on what you give it",
    explanation:
      "Each result cites your input and nothing else. Data Director checks that the agent " +
      "retrieved no records. It may use a language model.",
  },
  none: {
    label: "Works from your input by fixed rules",
    explanation:
      "Each result cites your input and nothing else. Data Director checks that the agent " +
      "retrieved no records and called no language model.",
  },
  delegation: {
    label: "Passes work to other agents",
    explanation:
      "Each result cites your input or a run of another agent it asked through Data Director. " +
      "Each of those runs is checked in its own right.",
  },
};

export const DERIVATION: Record<DerivationHow, string> = {
  template: "Filled in from a fixed template",
  model: "Written by a language model",
  lexical: "Matched by keyword rules",
  registry: "Taken from a registry record",
};

/** Words for a class name such as `DatasetProfile`: "dataset profile". */
/** Model providers by the name a manifest gives them. One not listed is shown as given. */
export const PROVIDER: Record<string, string> = {
  anthropic: "Anthropic",
};

/** How a model is run, from the card's `hosting`: where the input goes when the agent uses it. */
export const HOSTING: Record<"hosted" | "local", { label: string; explanation: string }> = {
  hosted: { label: "Remote", explanation: "runs on its provider's service, outside this institution" },
  local: { label: "Local", explanation: "runs on this institution's own infrastructure" },
};

export function className(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase();
}

/** Words for a slot or file name such as `media_types` or `soil-chemistry.profile`. */
export function fieldName(name: string): string {
  const words = name.replace(/[_.-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Short labels for a derivation, for a badge beside the value it describes. */
export const DERIVATION_SHORT: Record<DerivationHow, string> = {
  template: "Template",
  model: "Language model",
  lexical: "Keyword rules",
  registry: "Registry",
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
};

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
  "nothing-to-check": { label: "Nothing to check", tone: "plain" },
  "not-built": { label: "Not built yet", tone: "undeclared" },
};
