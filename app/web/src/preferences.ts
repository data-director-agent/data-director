/**
 * The person's preferences: how the app looks, how it writes dates and times, and which project
 * it opens in (docs/specs/app.md, "Preferences"). They are set on the Settings page, and the
 * colour scheme also from the banner's dark mode switch.
 *
 * Every choice is kept in this browser only, one `localStorage` key each, and none reaches the
 * server. Storage can be unavailable (a private window, blocked site data), so every read and
 * write tolerates failure: a choice that cannot be read is its default, and one that cannot be
 * written still applies to this page.
 *
 * The look is applied as attributes on <html>, which the tokens read (`tokens/neutral.css`):
 * `data-theme` (always `light` or `dark`, "Match system" being resolved here), `data-motion`,
 * `data-text-size` and `data-density` (absent at their defaults).
 */

import { useSyncExternalStore } from "react";

/** The choices for each preference; the first is the default. */
export const CHOICES = {
  theme: ["light", "dark", "system"],
  motion: ["system", "reduce", "full"],
  textSize: ["standard", "large", "larger"],
  density: ["comfortable", "compact"],
  dateLocale: ["browser", "en-GB", "en-US"],
  hourCycle: ["locale", "h23", "h12"],
  startupProject: ["last", "none"],
  personIcon: ["person", "researcher", "owl", "fox", "octopus", "seedling", "telescope", "books", "coffee"],
} as const;

/** The icon each `personIcon` choice shows beside "You" in the conversation, and its name. */
export const PERSON_ICONS: Record<Preferences["personIcon"], { icon: string; label: string }> = {
  person: { icon: "👤", label: "Person" },
  researcher: { icon: "🧑‍🔬", label: "Researcher" },
  owl: { icon: "🦉", label: "Owl" },
  fox: { icon: "🦊", label: "Fox" },
  octopus: { icon: "🐙", label: "Octopus" },
  seedling: { icon: "🌱", label: "Seedling" },
  telescope: { icon: "🔭", label: "Telescope" },
  books: { icon: "📚", label: "Books" },
  coffee: { icon: "☕", label: "Coffee" },
};

export type Preferences = { -readonly [K in keyof typeof CHOICES]: (typeof CHOICES)[K][number] };
export type PreferenceName = keyof Preferences;

/** The `localStorage` key of each preference. `dd-theme` predates the others and is kept. */
const KEYS: Record<PreferenceName, string> = {
  theme: "dd-theme",
  motion: "dd-motion",
  textSize: "dd-text-size",
  density: "dd-density",
  dateLocale: "dd-date-locale",
  hourCycle: "dd-hour-cycle",
  startupProject: "dd-startup-project",
  personIcon: "dd-person-icon",
};

const NAMES = Object.keys(CHOICES) as PreferenceName[];

function read<K extends PreferenceName>(name: K): Preferences[K] {
  const allowed: readonly string[] = CHOICES[name];
  let value: string | null = null;
  try {
    value = localStorage.getItem(KEYS[name]);
  } catch {
    // Storage is blocked: the default applies.
  }
  return (value !== null && allowed.includes(value) ? value : allowed[0]) as Preferences[K];
}

export const DEFAULTS = Object.fromEntries(NAMES.map((n) => [n, CHOICES[n][0]])) as Preferences;

export function storedPreferences(): Preferences {
  return Object.fromEntries(NAMES.map((n) => [n, read(n)])) as Preferences;
}

const DARK = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK).matches;
}

/** The scheme the page is drawn in: "Match system" is resolved to light or dark. */
export function resolvedTheme(theme: Preferences["theme"]): "light" | "dark" {
  if (theme === "system") return systemPrefersDark() ? "dark" : "light";
  return theme;
}

function setAttribute(name: string, value: string | null): void {
  const root = document.documentElement;
  if (value === null) root.removeAttribute(name);
  else root.setAttribute(name, value);
}

/** Draws the page as `preferences` say. */
export function applyPreferences(preferences: Preferences = storedPreferences()): void {
  setAttribute("data-theme", resolvedTheme(preferences.theme));
  setAttribute("data-motion", preferences.motion === "system" ? null : preferences.motion);
  setAttribute("data-text-size", preferences.textSize === "standard" ? null : preferences.textSize);
  setAttribute("data-density", preferences.density === "comfortable" ? null : preferences.density);
}

const listeners = new Set<() => void>();

/** Choices made while storage is blocked, which last until the page is reloaded. */
let unsaved: Partial<Preferences> = {};

/** Records a choice, applies it to the page and tells every component that shows it. */
export function setPreference<K extends PreferenceName>(name: K, value: Preferences[K]): void {
  try {
    localStorage.setItem(KEYS[name], value);
    unsaved = Object.fromEntries(Object.entries(unsaved).filter(([n]) => n !== name));
  } catch {
    // The choice still applies to this page; it is just not remembered.
    unsaved = { ...unsaved, [name]: value };
  }
  applyPreferences(currentPreferences());
  for (const listener of listeners) listener();
}

/** The current preferences, including any that could not be stored. */
export function currentPreferences(): Preferences {
  return { ...storedPreferences(), ...unsaved };
}

/** Applies the stored preferences now, before the first render, so that a dark choice does not
 * flash light, and redraws the page when the system's colour scheme changes while it is matched. */
export function startPreferences(): void {
  applyPreferences(currentPreferences());
  if (typeof window.matchMedia !== "function") return;
  window.matchMedia(DARK).addEventListener("change", () => {
    if (currentPreferences().theme === "system") {
      applyPreferences(currentPreferences());
      for (const listener of listeners) listener();
    }
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changing a choice changes it here too.
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || Object.values(KEYS).includes(event.key)) {
      applyPreferences(currentPreferences());
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

let snapshot: Preferences = DEFAULTS;

function getSnapshot(): Preferences {
  const now = currentPreferences();
  // The same object while nothing changed, as `useSyncExternalStore` requires.
  if (NAMES.some((n) => now[n] !== snapshot[n])) snapshot = now;
  return snapshot;
}

/** The preferences, re-rendering the caller when one changes. */
export function usePreferences(): Preferences {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULTS);
}
