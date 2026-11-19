/**
 * What `GET /api/agents` returns (app/src/dd_app/governance.py), as the shell reads it.
 *
 * Each manifest entry is the agent card's `agent-spec/v0` extension (`describe()` in
 * sdk/src/dd_sdk/agent.py, typed in `@data-director/agent-view` as `RawAgentSpec`) beside what
 * the deployment's profile assigns it. A field the shell does not know is ignored, not refused.
 *
 * Generated from the app's response models (`../api/generated/responses.ts`).
 */

export type { RawAgentsResponse, RawManifestEntry } from "../api/generated/responses";
