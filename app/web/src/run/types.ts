/**
 * What the run endpoints return, as generated from the app's response models
 * (`../api/generated/responses.ts`), and the checks' reports the run's event stream carries.
 *
 * The envelope is the contract's (sdk/src/dd_sdk/contract/models.py), typed in
 * `@data-director/agent-view`.
 *
 * TODO(#69): generate the contract's types from its JSON Schema. The run's AG-UI event stream is
 * read by `reduce.ts`.
 */

export type {
  Envelope,
  EvidenceItem,
  GroundingRef,
  ModelCall,
  OutcomeStatus,
  Problem,
} from "@data-director/agent-view";

export type { CheckReport, Checks, RunResult, RunRow, StoredRun } from "../api/generated/responses";

/**
 * The grounding check's report, as the harness's AG-UI binding sends it in `CUSTOM dd.grounding`
 * (`GroundingReport`, harness/src/dd_harness/grounding.py).
 */
export interface GroundingReport {
  passed: boolean;
  mode?: string | null;
  violations?: string[];
  retrieval_count?: number;
  chat_count?: number;
}

/**
 * The source check's report, as sent in `CUSTOM dd.sources` (`SourceReport`,
 * harness/src/dd_harness/sources.py).
 */
export interface SourceReport {
  passed: boolean;
  verified?: number;
  unresolved?: string[];
  violations?: string[];
}
