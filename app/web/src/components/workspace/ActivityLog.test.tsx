import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { useEffect } from "react";

import cancelledStream from "../../../cassettes/cancelled.jsonl?raw";
import delegatedStream from "../../../cassettes/delegated.jsonl?raw";
import { type ActivityRun, RunActivityProvider, useRunActivity } from "../../run/activity";
import { parseCassette } from "../../run/cassette";
import { reduceAll } from "../../run/reduce";
import { ActivityLog } from "./ActivityLog";

/** Records `runs`, oldest first, as streaming them would. */
function Recorded({ runs }: { runs: ActivityRun[] }) {
  const { record } = useRunActivity();
  useEffect(() => runs.forEach(record), [record, runs]);
  return null;
}

function run(key: string, conversationId: string, stream: string): ActivityRun {
  return {
    key,
    conversationId,
    startedAt: "2026-11-17T10:00:00Z",
    state: reduceAll(parseCassette(stream)),
  };
}

function renderLog(runs: ActivityRun[]) {
  return render(
    <RunActivityProvider>
      <Recorded runs={runs} />
      <ActivityLog />
    </RunActivityProvider>,
  );
}

describe("ActivityLog", () => {
  it("says no run has been sent from this tab yet", async () => {
    const { container } = renderLog([]);
    expect(screen.getByRole("heading", { level: 1, name: "Activity log" })).toBeVisible();
    expect(screen.getByText(/No runs in this tab yet/)).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("lists each step of each run, newest first, with a delegated run linked", async () => {
    const { container } = renderLog([
      run("a", "c1", delegatedStream),
      run("b", "c2", cancelledStream),
    ]);
    const runs = screen.getAllByRole("article");
    expect(runs).toHaveLength(2);
    // The newest run, cancelled, is first; its conversation is linked.
    expect(runs[0]).toHaveTextContent("Cancelled");
    expect(within(runs[0] as HTMLElement).getByRole("heading", { level: 2 })).toHaveTextContent(
      /^Run 2, sent at/,
    );
    expect(within(runs[0] as HTMLElement).getByRole("link", { name: "Open its conversation" }))
      .toHaveAttribute("href", "/?conversation=c2");
    const delegated = runs[1] as HTMLElement;
    expect(delegated).toHaveTextContent(/Finished/);
    expect(within(delegated).getByText(/Policy gate started/)).toBeInTheDocument();
    expect(within(delegated).getByText(/Delegated to example\.hello/)).toBeInTheDocument();
    const child = within(delegated).getAllByRole("link", { name: "open its run" })[0];
    expect(child?.getAttribute("href")).toMatch(/^\/\?run=/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("keeps a run's latest state, not one entry for each event", () => {
    const first = run("a", "c1", delegatedStream);
    renderLog([{ ...first, state: reduceAll([]) }, first]);
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });
});
