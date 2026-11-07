import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toHaveNoViolations } from "jest-axe";
import { afterEach, expect } from "vitest";

expect.extend(toHaveNoViolations);

/**
 * Empty React Aria's live announcer, as its `clearAnnouncer` does. A pending button that has
 * focus announces its label by adding `<div role="img" aria-labelledby>` to the announcer's logs
 * in `document.body`, outside Testing Library's container, and removes it only seven seconds
 * later. Tests share a DOM (`isolate: false`), so without this the entry outlives the button it
 * names and a later `axe(document.body)` finds an image with no name.
 */
function clearAnnouncer() {
  // A test file that runs under Node, such as `architecture.test.ts`, has no DOM.
  if (typeof document === "undefined") return;
  for (const log of document.querySelectorAll('[role="log"][aria-live]')) log.replaceChildren();
}

afterEach(() => {
  cleanup();
  clearAnnouncer();
});
