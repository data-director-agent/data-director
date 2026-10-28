/**
 * The dark mode switch in the banner. Light is the default; pressing it applies the dark
 * scheme and remembers the choice in this browser.
 */

import { useState } from "react";

import { applyTheme, storedTheme } from "../../theme";
import { ToggleButton } from "../ui/Button";

export function ThemeSwitch() {
  const [dark, setDark] = useState(() => storedTheme() === "dark");
  return (
    <ToggleButton
      className="theme-switch"
      variant="quiet"
      size="small"
      isSelected={dark}
      onChange={(selected) => {
        setDark(selected);
        applyTheme(selected ? "dark" : "light");
      }}
    >
      Dark mode
    </ToggleButton>
  );
}
