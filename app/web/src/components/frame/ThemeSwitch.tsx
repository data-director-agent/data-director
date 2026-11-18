/**
 * The dark mode switch in the banner. Light is the default; pressing it applies the dark
 * scheme and remembers the choice in this browser. It shows the scheme the page is drawn in, so
 * where the Settings page's preferences match the system it is pressed while the system is dark,
 * and pressing it then makes a fixed choice (`preferences.ts`).
 */

import { Moon } from "lucide-react";

import { resolvedTheme, setPreference, usePreferences } from "../../preferences";
import { ToggleButton } from "../ui/Button";

export function ThemeSwitch() {
  const { theme } = usePreferences();
  return (
    <ToggleButton
      className="theme-switch"
      variant="quiet"
      size="small"
      icon={Moon}
      isSelected={resolvedTheme(theme) === "dark"}
      onChange={(selected) => setPreference("theme", selected ? "dark" : "light")}
    >
      Dark mode
    </ToggleButton>
  );
}
