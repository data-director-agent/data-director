/**
 * The colour scheme: light by default, dark when the person chooses it.
 *
 * The choice is kept in this browser only. Storage can be unavailable (a private window,
 * blocked site data), so every read and write tolerates failure and falls back to light.
 */

export type Theme = "light" | "dark";

const KEY = "dd-theme";

export function storedTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // The choice still applies to this page; it is just not remembered.
  }
}
