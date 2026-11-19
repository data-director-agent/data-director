import { act, renderHook } from "@testing-library/react";

import {
  DEFAULTS,
  applyPreferences,
  resolvedTheme,
  setPreference,
  storedPreferences,
  usePreferences,
} from "./preferences";

const root = document.documentElement;

function matchSystem(dark: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: dark && query.includes("dark"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  localStorage.clear();
  for (const name of ["data-theme", "data-motion", "data-text-size", "data-density"]) {
    root.removeAttribute(name);
  }
  // jsdom has no matchMedia of its own.
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe("preferences", () => {
  it("are the defaults when nothing is stored", () => {
    expect(storedPreferences()).toEqual(DEFAULTS);
    expect(DEFAULTS.theme).toBe("light");
    expect(DEFAULTS.startupProject).toBe("last");
  });

  it("ignore a stored value that is not one of the choices", () => {
    localStorage.setItem("dd-text-size", "enormous");
    expect(storedPreferences().textSize).toBe(DEFAULTS.textSize);
  });

  it("keep the theme under the key it always had", () => {
    localStorage.setItem("dd-theme", "dark");
    expect(storedPreferences().theme).toBe("dark");
  });

  it("are stored, applied to <html> and leave no attribute at a default", () => {
    setPreference("textSize", "larger");
    setPreference("density", "compact");
    setPreference("motion", "reduce");
    expect(localStorage.getItem("dd-text-size")).toBe("larger");
    expect(root.dataset.textSize).toBe("larger");
    expect(root.dataset.density).toBe("compact");
    expect(root.dataset.motion).toBe("reduce");

    setPreference("textSize", "standard");
    setPreference("motion", "system");
    expect(root.hasAttribute("data-text-size")).toBe(false);
    expect(root.hasAttribute("data-motion")).toBe(false);
  });

  it("resolve matching the system to the scheme the system prefers", () => {
    expect(resolvedTheme("system")).toBe("light");
    matchSystem(true);
    expect(resolvedTheme("system")).toBe("dark");
    applyPreferences({ ...DEFAULTS, theme: "system" });
    expect(root.dataset.theme).toBe("dark");
  });

  it("still apply to the page when storage is blocked", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      setPreference("density", "compact");
      expect(root.dataset.density).toBe("compact");
    } finally {
      setItem.mockRestore();
      setPreference("density", "comfortable");
    }
  });

  it("re-render a component that shows them when one changes", () => {
    const { result } = renderHook(() => usePreferences());
    expect(result.current.hourCycle).toBe("locale");
    act(() => setPreference("hourCycle", "h12"));
    expect(result.current.hourCycle).toBe("h12");
  });
});
