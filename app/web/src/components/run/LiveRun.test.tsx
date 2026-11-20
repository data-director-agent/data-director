import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import failedGroundingStream from "../../../cassettes/failed-grounding.jsonl?raw";
import succeededStream from "../../../cassettes/succeeded.jsonl?raw";
import { parseCassette } from "../../run/cassette";
import { initialRunState, reduce, reduceAll, type RunState } from "../../run/reduce";
import { LiveRun } from "./LiveRun";

function draw(run: RunState, onCancel = vi.fn(), cancelling = false) {
  return render(
    <LiveRun run={run} cancelling={cancelling} onCancel={onCancel} idPrefix="t" />,
  );
}

/** The state after `events`, with the stream still open. */
function partway(events: readonly unknown[]): RunState {
  return events.reduce<RunState>((state, event) => reduce(state, event), initialRunState);
}

const stage = (label: string) =>
  within(screen.getByRole("region", { name: "Progress" })).getByText(label).closest("li");

describe("LiveRun", () => {
  it("says the run is starting before its plan arrives, and offers Cancel", async () => {
    const onCancel = vi.fn();
    const { container } = draw(partway([{ type: "RUN_STARTED", threadId: "t", runId: "r" }]), onCancel);
    expect(screen.getByText("Starting the run…")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Cancel the run" }));
    expect(onCancel).toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("keeps Cancel focused and busy once it has been asked for", () => {
    draw(partway(parseCassette(succeededStream).slice(0, 4)), vi.fn(), true);
    expect(screen.getByRole("button", { name: /Cancelling/ })).toBeInTheDocument();
  });

  it("tells a check that finished as passed or failed by its report", async () => {
    const { container } = draw(reduceAll(parseCassette(failedGroundingStream)));
    expect(stage("Grounding check")).toHaveTextContent("Failed");
    expect(stage("Agent")).toHaveTextContent("Done");
    // A run that finished has no Cancel and no screen of its own: the transcript shows it.
    expect(screen.queryByRole("button", { name: /Cancel/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: /Outcome/ })).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("groups unrecognised events, collapsed, and shows a malformed one as an error", async () => {
    const events = [
      ...parseCassette(succeededStream).slice(0, 3),
      { type: "SOMETHING_NEW" },
      { type: "CUSTOM", name: "vendor.extra", value: {} },
      { type: "SOMETHING_NEW" },
      { type: "STEP_STARTED" },
    ];
    const { container } = draw(partway(events));
    const group = screen.getByText("Unrecognised events (3)").closest("details");
    expect(group).not.toHaveAttribute("open");
    expect(within(group as HTMLElement).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Malformed event from server")).toBeVisible();
    // The run carries on.
    expect(screen.getByRole("button", { name: "Cancel the run" })).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("LiveRun while the agent works", () => {
  const plan = parseCassette(succeededStream).slice(0, 2);
  const agentRunning = [
    ...plan,
    { type: "STEP_STARTED", stepName: "gate" },
    { type: "STEP_FINISHED", stepName: "gate" },
    { type: "STEP_STARTED", stepName: "input" },
    { type: "STEP_FINISHED", stepName: "input" },
    { type: "STEP_STARTED", stepName: "agent" },
  ];

  afterEach(() => {
    vi.useRealTimers();
  });

  it("draws the agent's children and tool calls under its stage", async () => {
    const { container } = draw(
      partway([
        ...agentRunning,
        { type: "SUBAGENT_STARTED", subagentRunId: "c", name: "advisor.quality" },
        { type: "TOOL_CALL_START", toolCallId: "a", toolCallName: "spdx.get_licence" },
        { type: "TOOL_CALL_END", toolCallId: "a" },
      ]),
    );
    const done = within(stage("Agent") as HTMLElement).getByRole("list", {
      name: "What the agent has done",
    });
    expect(done).toHaveTextContent("Asking advisor.quality…");
    expect(done).toHaveTextContent("Used spdx.get_licence");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows only the latest few, and counts the rest", () => {
    const calls = Array.from({ length: 8 }, (_, i) => ({
      type: "TOOL_CALL_START",
      toolCallId: `t${i}`,
      toolCallName: `tool.n${i}`,
    }));
    draw(partway([...agentRunning, ...calls]));
    expect(screen.getByText("and 3 earlier")).toBeVisible();
    expect(screen.queryByText("tool.n2")).toBeNull();
    expect(screen.getByText("tool.n7")).toBeVisible();
  });

  it("counts the running stage's time, and says it is still working once the stream is quiet", () => {
    vi.useFakeTimers();
    draw(partway(agentRunning));
    expect(stage("Agent")).toHaveTextContent("Running · 0:00");
    expect(screen.queryByText(/Still working/)).toBeNull();
    act(() => vi.advanceTimersByTime(21_000));
    expect(stage("Agent")).toHaveTextContent("Running · 0:21");
    expect(screen.getByText(/Still working/)).toBeVisible();
  });

  it("stops counting once the run has ended", () => {
    draw(reduceAll(parseCassette(succeededStream)));
    expect(stage("Agent")).not.toHaveTextContent("·");
  });
});
