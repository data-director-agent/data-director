/**
 * What the agent is doing while its stage runs, as far as the stream says (docs/specs/app.md, "A
 * turn's run is drawn live"): each delegated child (`SUBAGENT_*`) and each tool call the harness's
 * gateway made for it (`TOOL_CALL_*`), in the order they started, drawn from the run log and
 * nothing else. The orchestrator's own model calls are not streamed (TODO(#159)), so nothing here
 * claims more than the events say.
 */

import type { RunState } from "./reduce";

export type ActivityState = "running" | "done" | "failed";

export interface ActivityItem {
  /** Unique in the run: the child's run id or the tool call's id. */
  key: string;
  kind: "subagent" | "tool";
  /** The child agent's id, or the tool's gateway name (`server.tool`). */
  name: string;
  state: ActivityState;
  /** A finished child's outcome status, in the contract's vocabulary. */
  status: string | null;
}

/** The agent's activity so far, in the order it started. */
export function agentActivity(state: RunState): ActivityItem[] {
  const items: ActivityItem[] = [];
  const at = new Map<string, number>();
  const put = (item: ActivityItem) => {
    const i = at.get(item.key);
    if (i === undefined) {
      at.set(item.key, items.length);
      items.push(item);
    } else {
      items[i] = { ...item, name: item.name || (items[i]?.name ?? "") };
    }
  };
  for (const entry of state.log) {
    if (entry.kind === "tool-call") {
      put({
        key: `tool:${entry.id}`,
        kind: "tool",
        name: entry.name,
        state: entry.done ? "done" : "running",
        status: null,
      });
    } else if (entry.kind === "subagent" && entry.runId !== null) {
      const key = `subagent:${entry.runId}`;
      const before = at.has(key) ? items[at.get(key) as number] : undefined;
      const state: ActivityState =
        entry.event === "SUBAGENT_FINISHED"
          ? "done"
          : entry.event === "SUBAGENT_ERROR"
            ? "failed"
            : (before?.state ?? "running");
      put({
        key,
        kind: "subagent",
        name: entry.name ?? before?.name ?? "",
        state,
        status: entry.status ?? before?.status ?? null,
      });
    }
  }
  return items;
}
