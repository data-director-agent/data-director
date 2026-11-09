/**
 * Reading a card that arrived as JSON. `readCard` never throws: what does not have the shape the
 * types describe is dropped and named in `issues`, so a page can show what it could read and say
 * what it could not. Conformance with the A2A specification is the A2A Inspector's job; this is
 * only enough checking that rendering cannot fail.
 */

import type { AgentCard, AgentExtension, AgentInterface, AgentSkill } from "./types";

export interface ReadCard {
  /** Null when the value is not a card at all: not an object, or no `name`. */
  card: AgentCard | null;
  issues: string[];
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] | undefined {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : undefined;
}

/** The items of `value` that `keep` accepts; each one it refuses is named in `issues`. */
function listOf<T>(
  value: unknown,
  what: string,
  issues: string[],
  keep: (item: unknown) => T | null,
): T[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) {
    issues.push(`${what} is not a list.`);
    return undefined;
  }
  const kept: T[] = [];
  value.forEach((item, i) => {
    const read = keep(item);
    if (read === null) issues.push(`${what} ${i + 1} is not readable.`);
    else kept.push(read);
  });
  return kept;
}

function skill(value: unknown): AgentSkill | null {
  if (!isRecord(value) || typeof value.id !== "string") return null;
  const tags = strings(value.tags);
  const examples = strings(value.examples);
  const inputModes = strings(value.inputModes);
  const outputModes = strings(value.outputModes);
  return {
    id: value.id,
    ...(typeof value.name === "string" ? { name: value.name } : {}),
    ...(typeof value.description === "string" ? { description: value.description } : {}),
    ...(tags ? { tags } : {}),
    ...(examples ? { examples } : {}),
    ...(inputModes ? { inputModes } : {}),
    ...(outputModes ? { outputModes } : {}),
  };
}

function extension(value: unknown): AgentExtension | null {
  if (!isRecord(value) || typeof value.uri !== "string") return null;
  return {
    uri: value.uri,
    ...(typeof value.description === "string" ? { description: value.description } : {}),
    ...(typeof value.required === "boolean" ? { required: value.required } : {}),
    ...(isRecord(value.params) ? { params: value.params } : {}),
  };
}

function agentInterface(value: unknown): AgentInterface | null {
  if (!isRecord(value) || typeof value.url !== "string") return null;
  return value as unknown as AgentInterface;
}

export function readCard(value: unknown): ReadCard {
  const issues: string[] = [];
  if (!isRecord(value)) return { card: null, issues: ["The card is not a JSON object."] };
  if (typeof value.name !== "string") {
    return { card: null, issues: ["The card has no name, so it is not an A2A agent card."] };
  }
  // Keep every field, then replace or drop those the types describe, so that what a newer card
  // adds still reaches a view that knows it.
  const {
    description,
    version,
    documentationUrl,
    iconUrl,
    defaultInputModes,
    defaultOutputModes,
    provider,
    supportedInterfaces,
    skills,
    capabilities,
    securitySchemes,
    ...rest
  } = value;
  const text = (key: string, v: unknown) => {
    if (v === undefined) return {};
    if (typeof v === "string") return { [key]: v };
    issues.push(`${key} is not text.`);
    return {};
  };
  const object = (key: string, v: unknown) => {
    if (v === undefined) return {};
    if (isRecord(v)) return { [key]: v };
    issues.push(`${key} is not an object.`);
    return {};
  };
  // In the order a card lists them, so that the issues do too.
  const texts = {
    ...text("description", description),
    ...text("version", version),
    ...text("documentationUrl", documentationUrl),
    ...text("iconUrl", iconUrl),
  };
  const providerPart = object("provider", provider);
  const inputs = strings(defaultInputModes);
  const outputs = strings(defaultOutputModes);
  const interfaces = listOf(supportedInterfaces, "Interface", issues, agentInterface);
  const readSkills = listOf(skills, "Skill", issues, skill);
  let caps: AgentCard["capabilities"] | undefined;
  if (isRecord(capabilities)) {
    const { extensions: rawExtensions, ...otherCaps } = capabilities;
    const extensions = listOf(rawExtensions, "Extension", issues, extension);
    caps = { ...otherCaps, ...(extensions ? { extensions } : {}) };
  } else if (capabilities !== undefined) {
    issues.push("capabilities is not an object.");
  }
  const card: AgentCard = {
    ...rest,
    name: value.name,
    ...texts,
    ...(inputs ? { defaultInputModes: inputs } : {}),
    ...(outputs ? { defaultOutputModes: outputs } : {}),
    ...providerPart,
    ...(interfaces ? { supportedInterfaces: interfaces } : {}),
    ...(readSkills ? { skills: readSkills } : {}),
    ...(caps ? { capabilities: caps } : {}),
    ...object("securitySchemes", securitySchemes),
  };
  return { card, issues };
}
