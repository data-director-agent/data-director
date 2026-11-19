import delegatedStream from "../../cassettes/delegated.jsonl?raw";
import { agentActivity } from "./agentActivity";
import { parseCassette } from "./cassette";
import { initialRunState, reduce, reduceAll, type RunState } from "./reduce";

const fold = (events: readonly unknown[]): RunState =>
  events.reduce<RunState>((state, event) => reduce(state, event), initialRunState);

const START = { type: "RUN_STARTED", threadId: "t", runId: "r" };

describe("what the agent is doing, from the run log", () => {
  it("draws a delegated child from start to its outcome", () => {
    const [child] = agentActivity(reduceAll(parseCassette(delegatedStream)));
    expect(child).toMatchObject({
      kind: "subagent",
      name: "example.hello",
      state: "done",
      status: "succeeded",
    });
  });

  it("draws tool calls by name, running until they end, in the order they started", () => {
    const run = fold([
      START,
      { type: "TOOL_CALL_START", toolCallId: "a", toolCallName: "spdx.get_licence" },
      { type: "TOOL_CALL_START", toolCallId: "b", toolCallName: "spdx.search_licences" },
      { type: "TOOL_CALL_END", toolCallId: "a" },
    ]);
    expect(agentActivity(run).map(({ name, state }) => [name, state])).toEqual([
      ["spdx.get_licence", "done"],
      ["spdx.search_licences", "running"],
    ]);
  });

  it("keeps a child's name when it fails", () => {
    const run = fold([
      START,
      { type: "SUBAGENT_STARTED", subagentRunId: "c", name: "advisor.quality" },
      { type: "SUBAGENT_ERROR", subagentRunId: "c", message: "no" },
    ]);
    expect(agentActivity(run)).toEqual([
      { key: "subagent:c", kind: "subagent", name: "advisor.quality", state: "failed", status: null },
    ]);
  });

  it("has nothing to say of a run that used no tools and asked no one", () => {
    expect(agentActivity(fold([START]))).toEqual([]);
  });
});
