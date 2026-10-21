/**
 * Plain-language wording for the contract's vocabulary.
 *
 * Kept in step with the LinkML descriptions in sdk/src/dd_sdk/schema/data_director.yaml and
 * with the linter's rules (harness/src/dd_harness/grounding.py). The wording states what the
 * harness checks and no more: a grounding check is a consistency check, not proof that an
 * agent retrieved anything (ADR-0016).
 */

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
export function className(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase();
}
