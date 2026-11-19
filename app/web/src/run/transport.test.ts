import { EventType, HttpAgent, type BaseEvent } from "@ag-ui/client";
import { renderHook } from "@testing-library/react";

import { CassetteAgent, parseCassette } from "./cassette";
import { READ_BY_NAME } from "./events";
import { reduceAll } from "./reduce";
import {
  cassetteTransport,
  httpTransport,
  streamRun,
  turnCancelUrl,
  turnStreamUrl,
  useRunTransport,
} from "./transport";

const TURN = { runId: "run", forwardedProps: { message_text: "hello" } };

/** Every cassette, by file name, so that a new one is replayed here without editing this test. */
const CASSETTES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("../../cassettes/*.jsonl", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ).map(([path, text]) => [path.split("/").pop() ?? path, text]),
);

/** The events a run gives `streamRun`, in order. */
async function replay(agent: CassetteAgent): Promise<BaseEvent[]> {
  const seen: BaseEvent[] = [];
  await streamRun(agent, TURN, (event) => seen.push(event)).done;
  return seen;
}

describe("CassetteAgent", () => {
  it("has a cassette to replay", () => {
    expect(Object.keys(CASSETTES).length).toBeGreaterThan(0);
  });

  it.each(Object.keys(CASSETTES))(
    "replays %s as the file holds it",
    async (name) => {
      const events = parseCassette(CASSETTES[name] ?? "");
      const seen = await replay(new CassetteAgent({ events }));
      expect(seen.map((event) => event.type)).toEqual(
        events.map((event) => (event as { type: string }).type),
      );
      // Each event arrives with every field the cassette gave it, unchanged.
      seen.forEach((event, i) => expect(event).toMatchObject(events[i] as object));
    },
  );

  it("paces the events when asked, and only then", async () => {
    vi.useFakeTimers();
    try {
      const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
      const seen: BaseEvent[] = [];
      const { done } = streamRun(new CassetteAgent({ events, paceMs: 100 }), TURN, (event) =>
        seen.push(event),
      );
      await vi.advanceTimersByTimeAsync(0);
      expect(seen.length).toBeLessThan(events.length);
      const before = seen.length;
      await vi.advanceTimersByTimeAsync(100);
      expect(seen.length).toBeGreaterThan(before);
      await vi.runAllTimersAsync();
      await done;
      expect(seen).toHaveLength(events.length);
    } finally {
      vi.useRealTimers();
    }
  });

  it("replays everything at once with pacing off", async () => {
    vi.useFakeTimers();
    try {
      const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
      const seen = await replay(new CassetteAgent({ events }));
      expect(seen).toHaveLength(events.length);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops when the run is stopped", async () => {
    vi.useFakeTimers();
    try {
      const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
      const agent = new CassetteAgent({ events, paceMs: 100 });
      const seen: BaseEvent[] = [];
      const run = streamRun(agent, TURN, (event) => seen.push(event));
      await vi.advanceTimersByTimeAsync(100);
      run.stop();
      const atAbort = seen.length;
      await vi.runAllTimersAsync();
      await run.done;
      expect(seen).toHaveLength(atAbort);
      expect(atAbort).toBeLessThan(events.length);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("cancelling a replay", () => {
  it("ends it as the harness ends a cancelled run, with the running step left open", async () => {
    vi.useFakeTimers();
    try {
      const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
      const transport = cassetteTransport(events, { paceMs: 100 });
      const seen: BaseEvent[] = [];
      const { done } = streamRun(transport.agentFor("c1"), TURN, (event) => seen.push(event));
      await vi.advanceTimersByTimeAsync(300);
      await transport.cancel("c1", "run");
      await done;
      const last = seen[seen.length - 1] as BaseEvent & { outcome?: { type: string } };
      expect(last.type).toBe(EventType.RUN_FINISHED);
      expect(last.outcome).toEqual({ type: "cancelled" });
      expect(seen.length).toBeLessThan(events.length);
      expect(reduceAll(seen).phase).toBe("cancelled");
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does nothing once the replay has ended", async () => {
    const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
    const transport = cassetteTransport(events);
    const seen: BaseEvent[] = [];
    await streamRun(transport.agentFor("c1"), TURN, (event) => seen.push(event)).done;
    await transport.cancel("c1", "run");
    expect(seen).toHaveLength(events.length);
  });
});

describe("the transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cancels a live turn at its cancel route, and takes a turn already ended as done", async () => {
    const fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 404 })));
    vi.stubGlobal("fetch", fetch);
    await expect(httpTransport.cancel("conv/1", "r 1")).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(
      "/api/conversations/conv%2F1/turns/r%201/cancel",
      expect.objectContaining({ method: "POST" }),
    );
    expect(turnCancelUrl("c", "r")).toBe("/api/conversations/c/turns/r/cancel");
    fetch.mockResolvedValueOnce(new Response(null, { status: 500 }));
    await expect(httpTransport.cancel("c", "r")).rejects.toThrow();
  });

  it("sends the turn in the conversation's thread", async () => {
    const agent = new CassetteAgent({ events: [], threadId: "c1" });
    const run = vi.spyOn(agent, "run");
    await streamRun(agent, TURN, () => undefined).done;
    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({ threadId: "c1", ...TURN, messages: [] }),
    );
  });

  it("rejects when the stream fails", async () => {
    const agent = new HttpAgent({
      url: "/x",
      threadId: "c1",
      fetch: () => Promise.resolve(new Response("{}", { status: 409 })),
    });
    await expect(streamRun(agent, TURN, () => undefined).done).rejects.toThrow();
  });

  it("streams a live turn from the conversation's stream route", () => {
    const agent = httpTransport.agentFor("conv/1");
    expect(agent).toBeInstanceOf(HttpAgent);
    expect((agent as HttpAgent).url).toBe(turnStreamUrl("conv/1"));
    expect(turnStreamUrl("conv/1")).toBe("/api/conversations/conv%2F1/turns/stream");
    expect(agent.threadId).toBe("conv/1");
  });

  it("replays a cassette in the conversation's thread", () => {
    const events = parseCassette(CASSETTES["succeeded.jsonl"] ?? "");
    const agent = cassetteTransport(events, { paceMs: 5 }).agentFor("c1");
    expect(agent).toBeInstanceOf(CassetteAgent);
    expect((agent as CassetteAgent).paceMs).toBe(5);
    expect(agent.threadId).toBe("c1");
  });

  it("is live unless a test or fixture provides another", () => {
    const { result } = renderHook(() => useRunTransport());
    expect(result.current).toBe(httpTransport);
  });
});

describe("the event names the shell reads", () => {
  it("are AG-UI's own", () => {
    const known = new Set<string>(Object.values(EventType));
    expect(READ_BY_NAME.filter((type) => !known.has(type))).toEqual([]);
  });
});
