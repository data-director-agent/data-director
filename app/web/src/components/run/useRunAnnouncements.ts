/**
 * Says a run's progress through the announcer as its state changes (#948): each step once, a
 * failed check, and the end, with errors in the assertive region (`run/announce.ts`). The run
 * view calls it with the reducer's state; a new run starts with nothing said.
 */

import { useEffect, useRef } from "react";

import { unsaid } from "../../run/announce";
import type { RunState } from "../../run/reduce";
import { useAnnounce } from "../ui/Announcer";

export function useRunAnnouncements(state: RunState): void {
  const announce = useAnnounce();
  const said = useRef<{ runId: string | null; keys: Set<string> }>({
    runId: state.runId,
    keys: new Set(),
  });
  useEffect(() => {
    // A different run, or the state set back to the start, begins with nothing said.
    const other = said.current.runId !== null && said.current.runId !== state.runId;
    if (other || state.phase === "idle") said.current = { runId: state.runId, keys: new Set() };
    else if (said.current.runId === null) said.current.runId = state.runId;
    for (const { key, message, assertive } of unsaid(state, said.current.keys)) {
      said.current.keys.add(key);
      announce(message, { assertive });
    }
  }, [announce, state]);
}
