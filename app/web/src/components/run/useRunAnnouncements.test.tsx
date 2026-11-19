import { render, screen } from "@testing-library/react";

import delegatedStream from "../../../cassettes/delegated.jsonl?raw";
import runErrorStream from "../../../cassettes/run-error.jsonl?raw";
import { parseCassette } from "../../run/cassette";
import { initialRunState, reduce, streamEnded, type RunState } from "../../run/reduce";
import { AnnouncerProvider } from "../ui/Announcer";
import { useRunAnnouncements } from "./useRunAnnouncements";

function Run({ state }: { state: RunState }) {
  useRunAnnouncements(state);
  return null;
}

/** Draws each state a stream gives, in turn, as the run view will, drawing each twice. */
function play(events: readonly unknown[]) {
  const view = render(
    <AnnouncerProvider>
      <Run state={initialRunState} />
    </AnnouncerProvider>,
  );
  let state = initialRunState;
  const draw = (next: RunState) => {
    for (let i = 0; i < 2; i += 1) {
      view.rerender(
        <AnnouncerProvider>
          <Run state={next} />
        </AnnouncerProvider>,
      );
    }
  };
  for (const event of events) {
    state = reduce(state, event);
    draw(state);
  }
  draw(streamEnded(state));
}

const polite = () => screen.getByRole("log", { name: "Announcements" });
const assertive = () => screen.getByRole("log", { name: "Errors" });

describe("useRunAnnouncements", () => {
  it("says each step once, politely, however often the state is drawn", () => {
    play(parseCassette(delegatedStream));
    const said = [...polite().children].map((p) => p.textContent);
    expect(new Set(said).size).toBe(said.length);
    expect(assertive()).toBeEmptyDOMElement();
  });

  it("says RUN_ERROR in the assertive region", () => {
    play(parseCassette(runErrorStream));
    expect(assertive().children).toHaveLength(1);
    expect(polite()).toBeEmptyDOMElement();
  });
});
