/**
 * An A2A 1.0 agent card as JSON: what an a2a-sdk `AgentCard` serialises to at
 * `/.well-known/agent-card.json` (protobuf JSON, so camelCase). Only `name` is required here;
 * every other field may be absent, and a field these types do not know is kept, not refused,
 * so that a newer card still reads.
 */

export interface AgentProvider {
  organization?: string;
  url?: string;
}

export interface AgentInterface {
  url: string;
  protocolBinding?: string;
  protocolVersion?: string;
  tenant?: string;
}

export interface AgentExtension {
  uri: string;
  description?: string;
  required?: boolean;
  params?: Record<string, unknown>;
}

export interface AgentCapabilities {
  streaming?: boolean;
  pushNotifications?: boolean;
  extendedAgentCard?: boolean;
  extensions?: AgentExtension[];
}

export interface AgentSkill {
  id: string;
  name?: string;
  description?: string;
  tags?: string[];
  examples?: string[];
  inputModes?: string[];
  outputModes?: string[];
}

/** A security scheme is a oneof: its one key names the kind, such as `apiKeySecurityScheme`. */
export type SecurityScheme = Record<string, { description?: string } & Record<string, unknown>>;

export interface AgentCard {
  name: string;
  description?: string;
  version?: string;
  provider?: AgentProvider;
  documentationUrl?: string;
  iconUrl?: string;
  supportedInterfaces?: AgentInterface[];
  capabilities?: AgentCapabilities;
  securitySchemes?: Record<string, SecurityScheme>;
  defaultInputModes?: string[];
  defaultOutputModes?: string[];
  skills?: AgentSkill[];
  signatures?: unknown[];
  [key: string]: unknown;
}
