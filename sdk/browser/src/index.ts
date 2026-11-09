/**
 * `@data-director/agent-view`: reading Data Director A2A agent cards and their payloads.
 *
 * This entry point is headless (no React), so any page can read a card with it. The components
 * are at `@data-director/agent-view/react`, their styles at `@data-director/agent-view/styles.css`.
 */

export type {
  AgentCapabilities,
  AgentCard,
  AgentExtension,
  AgentInterface,
  AgentProvider,
  AgentSkill,
  SecurityScheme,
} from "./card/types";
export { isRecord, type ReadCard, readCard } from "./card/read";
export {
  AGENT_SPEC_URI,
  agentSpecOf,
  extensionsOf,
  findExtension,
  MANIFEST_URI,
  manifestOf,
} from "./card/extensions";
export type {
  DerivationHow,
  GroundingMode,
  RawAgentSpec,
  RawDerived,
  RawModelUse,
  RawSchemaEntry,
} from "./spec/types";
export {
  type AgentSpec,
  agentName,
  type Derivation,
  readAgentSpec,
  specFromRaw,
} from "./spec/read";
export {
  type JsonSchema,
  properties,
  resolve,
  type ScalarType,
  type Shape,
  shapeOf,
} from "./schema/shape";
export type {
  Envelope,
  EvidenceItem,
  GroundingRef,
  Outcome,
  OutcomeStatus,
  Problem,
} from "./payload/types";
export { evidenceAnchor, evidenceKey } from "./payload/evidence";
export { type Context, isEmpty, makeContext, recorders } from "./payload/context";
export { DOCUMENT_TEXT, type DocumentPart, documentOf } from "./payload/document";
export { className, DERIVATION, DERIVATION_SHORT, fieldName } from "./wording";
