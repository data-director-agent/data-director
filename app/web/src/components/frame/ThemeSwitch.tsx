/**
 * The dark mode switch in the banner. Light is the default; pressing it applies the dark
 * scheme and remembers the choice in this browser.
 */

import { useState } from "react";
import { ToggleButton } from "react-aria-components";

import { applyTheme, storedTheme } from "../../theme";

export function ThemeSwitch() {
  const [dark, setDark] = useState(() => storedTheme() === "dark");
  return (
    <ToggleButton
      className="theme-switch"
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
