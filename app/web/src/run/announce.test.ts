import delegatedStream from "../../cassettes/delegated.jsonl?raw";
import failedGroundingStream from "../../cassettes/failed-grounding.jsonl?raw";
import runErrorStream from "../../cassettes/run-error.jsonl?raw";
import { type Announcement, unsaid } from "./announce";
import { parseCassette } from "./cassette";
import { initialRunState, reduce, streamEnded, type RunState } from "./reduce";

/**
 * Replays events through the reducer as a stream would deliver them, saying after each event
 * what has not yet been said, as the announcer does. `closed` also ends the stream.
 */
function replay(events: readonly unknown[], { closed = true } = {}): Announcement[] {
  const said = new Set<string>();
  const spoken: Announcement[] = [];
  const speak = (state: RunState) => {
    for (const announcement of unsaid(state, said)) {
      said.add(announcement.key);
      spoken.push(announcement);
    }
  };
  let state = initialRunState;
  for (const event of events) {
    state = reduce(state, event);
    speak(state);
  }
  if (closed) speak(streamEnded(state));
  return spoken;
}

const shape = (spoken: Announcement[]) => spoken.map(({ key, assertive }) => [key, assertive]);

describe("the announcements for a run, replayed through the reducer", () => {
  it("says each step of a long multi-step run once, in order, then its end, all politely", () => {
    expect(shape(replay(parseCassette(delegatedStream)))).toEqual([
      ["step:gate", false],
      ["step:input", false],
      ["step:agent", false],
      ["step:grounding", false],
      ["step:sources", false],
      ["end", false],
    ]);
  });

  it("names each step by the plan's label", () => {
    const events = parseCassette(delegatedStream);
    const plan = events.find(
      (e) => (e as { name?: string }).name === "dd.plan",
    ) as { value: { steps: { id: string; label: string }[] } };
    const spoken = replay(events).filter(({ key }) => key.startsWith("step:"));
    spoken.forEach((announcement, i) =>
      expect(announcement.message).toContain(plan.value.steps[i]?.label),
    );
  });

  it("does not say a step again when its events repeat", () => {
    const events = parseCassette(delegatedStream);
    const doubled = events.flatMap((e) =>
      (e as { type?: string }).type?.startsWith("STEP_") ? [e, e] : [e],
    );
    expect(shape(replay(doubled))).toEqual(shape(replay(events)));
  });

  it("says a failed check politely, before the end", () => {
    const keys = replay(parseCassette(failedGroundingStream)).map(({ key }) => key);
    expect(keys).toContain("report:grounding");
    expect(keys.indexOf("report:grounding")).toBeLessThan(keys.indexOf("end"));
    expect(keys).not.toContain("report:sources");
  });
});

describe("errors go to the assertive region", () => {
  it("RUN_ERROR, with its message", () => {
    const spoken = replay(parseCassette(runErrorStream));
    expect(shape(spoken)).toEqual([["end", true]]);
    expect(spoken[0]?.message).toContain("no.such.agent");
  });

  it("each malformed event, and the run carries on", () => {
    const events = parseCassette(delegatedStream);
    const spoken = replay([...events.slice(0, 4), { type: "STEP_STARTED" }, ...events.slice(4)]);
    expect(shape(spoken).filter(([, assertive]) => assertive)).toEqual([["malformed:1", true]]);
    expect(spoken.at(-1)).toMatchObject({ key: "end", assertive: false });
  });

  it("a stream that closes before the run ends", () => {
    const events = parseCassette(delegatedStream);
    const spoken = replay(events.slice(0, 7));
    expect(spoken.at(-1)).toMatchObject({ key: "end", assertive: true });
  });

  it("nothing while the stream is still open", () => {
    const events = parseCassette(delegatedStream);
    expect(replay(events.slice(0, 7), { closed: false }).some(({ key }) => key === "end")).toBe(
      false,
    );
  });
});
