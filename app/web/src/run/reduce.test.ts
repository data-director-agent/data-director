import abstainedStream from "../../cassettes/abstained.jsonl?raw";
import cancelledStream from "../../cassettes/cancelled.jsonl?raw";
import failedGroundingStream from "../../cassettes/failed-grounding.jsonl?raw";
import referredStream from "../../cassettes/referred.jsonl?raw";
import runErrorStream from "../../cassettes/run-error.jsonl?raw";
import succeededStream from "../../cassettes/succeeded.jsonl?raw";
import { parseCassette as events } from "./cassette";
import { initialRunState, reduce, reduceAll, streamEnded, type RunState } from "./reduce";

/** What the run view draws from a state, without the envelope's full contents. */
function summary(state: RunState) {
  return {
    phase: state.phase,
    steps: state.steps.map((step) => [step.id, step.state]),
    status: state.envelope?.outcome.status ?? null,
    grounding: state.grounding?.passed ?? null,
    sources: state.sources?.passed ?? null,
    error: state.error,
    unrecognised: state.unrecognised.count,
    malformed: state.malformed,
  };
}

const ALL_FINISHED = [
  ["gate", "finished"],
  ["input", "finished"],
  ["agent", "finished"],
  ["grounding", "finished"],
  ["sources", "finished"],
];

/** Freezes a state and everything in it, so a test fails if the reducer changes its input. */
function deepFreeze<T>(value: T): T {
  if (typeof value === "object" && value !== null) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

describe("each cassette reaches its expected state", () => {
  it("succeeded: every step finished and both checks passed", () => {
    expect(summary(reduceAll(events(succeededStream)))).toEqual({
      phase: "finished",
      steps: ALL_FINISHED,
      status: "succeeded",
      grounding: true,
      sources: true,
      error: null,
      unrecognised: 0,
      malformed: 0,
    });
  });

  it("abstained: every step finished, and the outcome says so", () => {
    expect(summary(reduceAll(events(abstainedStream)))).toMatchObject({
      phase: "finished",
      steps: ALL_FINISHED,
      status: "abstained",
      grounding: true,
      sources: true,
    });
  });

  it("failed-grounding: the grounding check failed and the run failed", () => {
    const state = reduceAll(events(failedGroundingStream));
    expect(summary(state)).toMatchObject({
      phase: "finished",
      steps: ALL_FINISHED,
      status: "failed",
      grounding: false,
      sources: true,
    });
    expect(state.grounding?.violations).toHaveLength(1);
  });

  it("referred: the input check and the agent were not reached", () => {
    expect(summary(reduceAll(events(referredStream)))).toMatchObject({
      phase: "finished",
      steps: [
        ["gate", "finished"],
        ["input", "not-reached"],
        ["agent", "not-reached"],
        ["grounding", "finished"],
        ["sources", "finished"],
      ],
      status: "referred",
    });
  });

  it("cancelled: the agent was stopped, the checks were not reached, and there is no envelope", () => {
    expect(summary(reduceAll(events(cancelledStream)))).toEqual({
      phase: "cancelled",
      steps: [
        ["gate", "finished"],
        ["input", "finished"],
        ["agent", "stopped"],
        ["grounding", "not-reached"],
        ["sources", "not-reached"],
      ],
      status: null,
      grounding: null,
      sources: null,
      error: null,
      unrecognised: 0,
      malformed: 0,
    });
  });

  it("run-error: an error with its message, and no steps", () => {
    expect(summary(reduceAll(events(runErrorStream)))).toEqual({
      phase: "error",
      steps: [],
      status: null,
      grounding: null,
      sources: null,
      error: "no agent registered as 'no.such.agent'; known: ['advisor.standards']",
      unrecognised: 0,
      malformed: 0,
    });
  });

  it("keeps the run's ids and the plan's labels", () => {
    const state = reduceAll(events(succeededStream));
    expect([state.threadId, state.runId]).toEqual(["thread", "run"]);
    expect(state.steps.map((step) => step.label)).toEqual([
      "Policy gate",
      "Input check",
      "Agent",
      "Grounding check",
      "Source check",
    ]);
  });

  it("logs each step and report in order", () => {
    const { log } = reduceAll(events(cancelledStream));
    expect(log).toEqual([
      { kind: "step-started", step: "gate" },
      { kind: "step-finished", step: "gate" },
      { kind: "step-started", step: "input" },
      { kind: "step-finished", step: "input" },
      { kind: "step-started", step: "agent" },
    ]);
  });
});

describe("while a run streams", () => {
  it("shows the running step and the steps still waiting", () => {
    const upToAgent = events(succeededStream).slice(0, 7);
    const state = upToAgent.reduce<RunState>(reduce, initialRunState);
    expect(summary(state)).toMatchObject({
      phase: "running",
      steps: [
        ["gate", "finished"],
        ["input", "finished"],
        ["agent", "running"],
        ["grounding", "waiting"],
        ["sources", "waiting"],
      ],
    });
  });

  it("is interrupted when the stream closes before the run finishes", () => {
    const state = reduceAll(events(succeededStream).slice(0, 7));
    expect(summary(state)).toMatchObject({
      phase: "interrupted",
      steps: [
        ["gate", "finished"],
        ["input", "finished"],
        ["agent", "stopped"],
        ["grounding", "not-reached"],
        ["sources", "not-reached"],
      ],
      status: null,
    });
  });

  it("is interrupted when the stream closes with no events at all", () => {
    expect(reduceAll([]).phase).toBe("interrupted");
  });

  it("leaves a finished run as it was when the stream closes", () => {
    const finished = reduceAll(events(succeededStream));
    expect(streamEnded(finished)).toBe(finished);
  });

  it("never changes the state it is given", () => {
    let state = deepFreeze(initialRunState);
    for (const event of events(succeededStream)) state = deepFreeze(reduce(state, event));
    expect(state.phase).toBe("finished");
  });

  it("adds a step the plan did not name, labelled with its id", () => {
    const state = reduceAll([
      { type: "RUN_STARTED", threadId: "t", runId: "r" },
      { type: "STEP_STARTED", stepName: "review" },
    ]);
    expect(state.steps).toEqual([{ id: "review", label: "review", state: "stopped" }]);
  });
});

describe("events the run view does not draw as steps", () => {
  const started = reduce(initialRunState, { type: "RUN_STARTED", threadId: "t", runId: "r" });

  it("shows a reply only once its message has ended", () => {
    let state = reduce(started, { type: "TEXT_MESSAGE_START", messageId: "m" });
    state = reduce(state, { type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "Hello, " });
    state = reduce(state, { type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "world" });
    expect(state.messages).toEqual([]);
    state = reduce(state, { type: "TEXT_MESSAGE_END", messageId: "m" });
    expect(state.messages).toEqual([{ id: "m", text: "Hello, world" }]);
    expect(state.pending).toEqual({});
  });

  it("counts reasoning without logging it", () => {
    let state = reduce(started, { type: "REASONING_START", messageId: "x" });
    state = reduce(state, { type: "REASONING_MESSAGE_CONTENT", messageId: "x", delta: "hmm" });
    expect(state.reasoning).toBe(2);
    expect(state.log).toEqual([]);
  });

  it("makes one log entry for a tool call, done when it ends", () => {
    let state = reduce(started, {
      type: "TOOL_CALL_START",
      toolCallId: "c1",
      toolCallName: "search_registry",
    });
    state = reduce(state, { type: "TOOL_CALL_ARGS", toolCallId: "c1", delta: "{}" });
    expect(state.log).toEqual([
      { kind: "tool-call", id: "c1", name: "search_registry", done: false },
    ]);
    state = reduce(state, { type: "TOOL_CALL_END", toolCallId: "c1" });
    expect(state.log).toEqual([
      { kind: "tool-call", id: "c1", name: "search_registry", done: true },
    ]);
  });

  it("logs subagent events", () => {
    const state = reduce(started, { type: "SUBAGENT_STARTED", name: "child" });
    expect(state.log).toEqual([{ kind: "subagent", event: "SUBAGENT_STARTED" }]);
  });

  it("counts unknown types and CUSTOM names once each, without throwing", () => {
    let state = reduce(started, { type: "STATE_SNAPSHOT", snapshot: {} });
    state = reduce(state, { type: "STATE_SNAPSHOT", snapshot: {} });
    state = reduce(state, { type: "CUSTOM", name: "dd.future", value: {} });
    expect(state.unrecognised).toEqual({ count: 3, types: ["STATE_SNAPSHOT", "CUSTOM dd.future"] });
    expect(state.phase).toBe("running");
  });

  it("counts an event after the run has ended, and does not apply it", () => {
    const finished = reduceAll(events(succeededStream));
    const state = reduce(finished, { type: "STEP_STARTED", stepName: "gate" });
    expect(state.steps).toEqual(finished.steps);
    expect(state.unrecognised.types).toEqual(["STEP_STARTED after the run ended"]);
  });

  it.each([
    ["no event at all", null, "an event without a type"],
    ["an event without a type", {}, "an event without a type"],
    ["a step without a name", { type: "STEP_STARTED" }, "STEP_STARTED without a step name"],
    [
      "a plan without steps",
      { type: "CUSTOM", name: "dd.plan", value: {} },
      "dd.plan without a list of steps",
    ],
    [
      "a report without a result",
      { type: "CUSTOM", name: "dd.grounding", value: { mode: "none" } },
      "dd.grounding without a pass or fail",
    ],
    [
      "a finish without an envelope",
      { type: "RUN_FINISHED", result: {} },
      "RUN_FINISHED without an envelope or a cancelled outcome",
    ],
  ])("counts and logs a malformed event: %s", (_name, event, reason) => {
    const state = reduce(started, event);
    expect(state.malformed).toBe(1);
    expect(state.log).toEqual([{ kind: "malformed", reason }]);
    expect(state.phase).toBe("running");
  });
});
