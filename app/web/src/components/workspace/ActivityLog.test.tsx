import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { useEffect } from "react";

import cancelledStream from "../../../cassettes/cancelled.jsonl?raw";
import delegatedStream from "../../../cassettes/delegated.jsonl?raw";
import { type ActivityRun, RunActivityProvider, useRunActivity } from "../../run/activity";
import { type RunApi, RunApiContext, type RunPage } from "../../run/api";
import type { RunRow } from "../../run/types";
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

function row(invocationId: string, status: RunRow["status"] = "succeeded"): RunRow {
  return {
    invocation_id: invocationId,
    agent_id: "example.hello",
    status,
    completed_at: "2026-11-17T10:00:05Z",
    acting_for: null,
  };
}

/** A run store holding `pages`, the first page first; each names the next by its index. */
function store(...pages: RunRow[][]) {
  const list = vi.fn((before?: string | null): Promise<RunPage> => {
    const index = before ? Number(before) : 0;
    const next = index + 1 < pages.length ? String(index + 1) : null;
    return Promise.resolve({ items: pages[index] ?? [], next });
  });
  return { list, get: vi.fn() } satisfies RunApi;
}

function renderLog(runs: ActivityRun[], api: RunApi = store([])) {
  return render(
    <RunApiContext.Provider value={api}>
      <RunActivityProvider>
        <Recorded runs={runs} />
        <ActivityLog />
      </RunActivityProvider>
    </RunApiContext.Provider>,
  );
}

const recorded = () => screen.findByRole("region", { name: "Recorded runs" });

describe("ActivityLog", () => {
  it("lists no run when none has been sent or recorded", async () => {
    const { container } = renderLog([]);
    expect(screen.getByRole("heading", { level: 1, name: "Activity log" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Sent from this tab" })).not.toBeInTheDocument();
    const section = await recorded();
    await waitFor(() => expect(within(section).queryByRole("status")).not.toBeInTheDocument());
    expect(within(section).queryByRole("table")).not.toBeInTheDocument();
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
    expect(within(runs[0] as HTMLElement).getByRole("heading", { level: 3 })).toHaveTextContent(
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

  it("badges each run's state and folds the older runs' steps away", () => {
    renderLog([run("a", "c1", delegatedStream), run("b", "c2", cancelledStream)]);
    const [newest, older] = screen.getAllByRole("article") as HTMLElement[];
    expect(within(newest as HTMLElement).getByText("Cancelled")).toHaveClass("status-warn");
    expect(screen.getByText("2 runs, newest first.")).toBeVisible();
    const open = (el: HTMLElement) => el.querySelector("details")?.hasAttribute("open");
    expect(open(newest as HTMLElement)).toBe(true);
    expect(open(older as HTMLElement)).toBe(false);
  });

  it("keeps a run's latest state, not one entry for each event", () => {
    const first = run("a", "c1", delegatedStream);
    renderLog([{ ...first, state: reduceAll([]) }, first]);
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("lists the recorded runs, each linked to its record, after a reload", async () => {
    const { container } = renderLog([], store([row("r2", "abstained"), row("r1")]));
    const section = await recorded();
    const items = (await within(section).findAllByRole("row")).slice(1);
    expect(items).toHaveLength(2);
    expect(within(items[0] as HTMLElement).getByRole("link")).toHaveAttribute("href", "/?run=r2");
    expect(within(items[0] as HTMLElement).getByText(/Abstained/)).toHaveClass("status-warn");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("still lists the recorded runs after leaving the page and coming back", async () => {
    const api = store([row("r1")]);
    const first = renderLog([], api);
    expect(await within(await recorded()).findAllByRole("row")).toHaveLength(2);
    first.unmount();
    renderLog([], api);
    expect(await within(await recorded()).findAllByRole("row")).toHaveLength(2);
  });

  it("does not list again a run this tab shows step by step", async () => {
    const delegated = run("a", "c1", delegatedStream);
    const own = delegated.state.envelope?.invocation_id;
    expect(own).toBeTruthy();
    renderLog([delegated], store([row(own as string), row("other")]));
    const items = (await within(await recorded()).findAllByRole("row")).slice(1);
    expect(items).toHaveLength(1);
    expect(within(items[0] as HTMLElement).getByRole("link")).toHaveAttribute("href", "/?run=other");
  });

  it("shows older runs a page at a time", async () => {
    const api = store([row("r2")], [row("r1")]);
    renderLog([], api);
    const section = await recorded();
    await within(section).findByRole("table");
    await userEvent.click(within(section).getByRole("button", { name: "Show older runs" }));
    await waitFor(() => expect(within(section).getAllByRole("row")).toHaveLength(3));
    expect(api.list).toHaveBeenLastCalledWith("1");
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
  });

  it("says when the recorded runs cannot be read, and still shows this tab's", async () => {
    const api = { list: () => Promise.reject(new Error("down")), get: vi.fn() } as RunApi;
    renderLog([run("a", "c1", cancelledStream)], api);
    expect(await within(await recorded()).findByRole("alert")).toBeVisible();
    expect(screen.getByRole("region", { name: "Sent from this tab" })).toBeVisible();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });
});
