/**
 * The providers a person's own AI account can be with, as the Settings page names them
 * (docs/specs/model-accounts.md, Enrolment).
 */

import type { ModelAccountProvider } from "../../session/api";

export const COMPATIBLE = "openai-compatible";

interface Described {
  name: string;
  key: string;
  hint: string;
  /** The provider's own page for creating a key, where it has one. */
  keysUrl?: string;
}

/** How the page names each provider the broker serves, and where a person gets a key. */
const PROVIDERS: Record<string, Described> = {
  anthropic: {
    name: "Anthropic",
    key: "Anthropic API key",
    hint: "Create a key in the Claude Console and paste it here.",
    keysUrl: "https://platform.claude.com/settings/keys",
  },
  openai: {
    name: "OpenAI",
    key: "OpenAI API key",
    hint: "Create a key in the OpenAI dashboard and paste it here.",
    keysUrl: "https://platform.openai.com/api-keys",
  },
  gemini: {
    name: "Google Gemini",
    key: "Gemini API key",
    hint: "Create a key in Google AI Studio and paste it here.",
    keysUrl: "https://aistudio.google.com/app/apikey",
  },
  [COMPATIBLE]: {
    name: "A model service your institution runs",
    key: "API key for the service",
    hint: "Ask the people who run the service for a key, and paste it here.",
  },
};

/** Where an account is offered when the server names no providers: Anthropic, as before. */
export const DEFAULT_PROVIDERS: ModelAccountProvider[] = [{ provider: "anthropic", baseUrls: [] }];

export function describe(provider: string): Described {
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

/** Key prefixes the hosted providers publish, most specific first. A key is checked by the broker;
 * this only spares a person pasting a key under the wrong provider. */
const PREFIXES: [string, string | null][] = [
  ["sk-ant-", "anthropic"],
  ["sk-or-", null],
  ["AIza", "gemini"],
  ["sk-", "openai"],
];

/** The hosted provider a key's prefix suggests, or `null` if it suggests none. */
export function guessProvider(key: string): string | null {
  const typed = key.trim();
  const match = PREFIXES.find(([prefix]) => typed.startsWith(prefix));
  return match ? match[1] : null;
}
