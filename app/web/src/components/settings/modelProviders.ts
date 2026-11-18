/**
 * The providers a person's own AI account can be with, as the Settings page names them
 * (docs/specs/model-accounts.md, Enrolment).
 */

import type { ModelAccountProvider } from "../../session/api";

export const COMPATIBLE = "openai-compatible";

/** How the page names each provider the broker serves, and where a person gets a key. */
const PROVIDERS: Record<string, { name: string; key: string; hint: string }> = {
  anthropic: {
    name: "Anthropic",
    key: "Anthropic API key",
    hint: "Create a key in the Anthropic Console and paste it here.",
  },
  openai: {
    name: "OpenAI",
    key: "OpenAI API key",
    hint: "Create a key in the OpenAI dashboard and paste it here.",
  },
  gemini: {
    name: "Google Gemini",
    key: "Gemini API key",
    hint: "Create a key in Google AI Studio and paste it here.",
  },
  [COMPATIBLE]: {
    name: "A model service your institution runs",
    key: "API key for the service",
    hint: "Ask the people who run the service for a key, and paste it here.",
  },
};

/** Where an account is offered when the server names no providers: Anthropic, as before. */
export const DEFAULT_PROVIDERS: ModelAccountProvider[] = [{ provider: "anthropic", baseUrls: [] }];

export function describe(provider: string) {
  return (
    PROVIDERS[provider] ?? {
      name: provider,
      key: "API key",
      hint: "Paste the key here.",
    }
  );
}

/** Whether `url` is an `https` address under one of `origins`, as the profile lists them. */
export function underOrigin(url: string, origins: string[]): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  return parsed.protocol === "https:" && origins.includes(parsed.origin);
}
