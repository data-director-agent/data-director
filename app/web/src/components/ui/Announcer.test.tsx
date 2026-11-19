import { act, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { type Announce, AnnouncerProvider, useAnnounce } from "./Announcer";

/** Renders the provider, handing back its `announce`. */
function mount() {
  let announce: Announce = () => undefined;
  function Speaker() {
    announce = useAnnounce();
    return null;
  }
  const view = render(
    <AnnouncerProvider>
      <Speaker />
    </AnnouncerProvider>,
  );
  return { ...view, announce: (...args: Parameters<Announce>) => act(() => announce(...args)) };
}

const polite = () => screen.getByRole("log", { name: "Announcements" });
const assertive = () => screen.getByRole("log", { name: "Errors" });

describe("AnnouncerProvider", () => {
  it("has both regions, empty, before anything is said", async () => {
    const { container } = mount();
    expect(polite()).toHaveAttribute("aria-live", "polite");
    expect(polite()).toHaveAttribute("aria-atomic", "false");
    expect(assertive()).toHaveAttribute("aria-live", "assertive");
    expect(polite()).toBeEmptyDOMElement();
    expect(assertive()).toBeEmptyDOMElement();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says a message politely unless it is assertive", () => {
    const { announce } = mount();
    announce("Step started.");
    announce("The run failed.", { assertive: true });
    expect(polite()).toHaveTextContent("Step started.");
    expect(polite()).not.toHaveTextContent("The run failed.");
    expect(assertive()).toHaveTextContent("The run failed.");
  });

  it("adds a repeated message as a new entry, so it is heard again", () => {
    const { announce } = mount();
    announce("Waiting.");
    announce("Waiting.");
    expect(polite().children).toHaveLength(2);
  });

  it("ignores an empty message and keeps only the last few entries", () => {
    const { announce } = mount();
    announce("");
    expect(polite()).toBeEmptyDOMElement();
    for (let i = 0; i < 20; i += 1) announce(`Message ${i}.`);
    expect(polite().children.length).toBeLessThan(20);
    expect(polite().lastElementChild).toHaveTextContent("Message 19.");
  });
});

describe("useAnnounce", () => {
  it("fails without a provider, rather than saying nothing", () => {
    function Speaker() {
      useAnnounce();
      return null;
    }
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Speaker />)).toThrow(/AnnouncerProvider/);
    error.mockRestore();
  });
});
