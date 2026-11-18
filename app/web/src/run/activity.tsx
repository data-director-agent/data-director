/**
 * The runs this tab has streamed, for the activity log (#69, #949): each conversation turn's run
 * state, as its stream arrives, newest first.
 *
 * The server keeps a run's record, not its events, so the log holds only what this tab has seen
 * since it was opened; a reload or signing out starts it empty. A run is recorded under the AG-UI
 * `runId` the shell gave it, which is unique to this tab, not the one the stream names (a replayed
 * cassette names the run it recorded).
 */

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import type { RunState } from "./reduce";

export interface ActivityRun {
  /** The `runId` the shell sent with the turn. */
  key: string;
  conversationId: string;
  /** When the turn was sent, as an ISO 8601 timestamp. */
  startedAt: string;
  state: RunState;
}

export interface RunActivity {
  /** The runs, newest first. */
  runs: readonly ActivityRun[];
  /** Records a run's latest state, adding the run if it is new. */
  record(run: ActivityRun): void;
}

/** Outside a provider, nothing is recorded: a component can be drawn on its own in a test. */
const NOWHERE: RunActivity = { runs: [], record: () => undefined };

const RunActivityContext = createContext<RunActivity>(NOWHERE);

export function RunActivityProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<readonly ActivityRun[]>([]);
  const record = useCallback((run: ActivityRun) => {
    setRuns((held) =>
      held.some((r) => r.key === run.key)
        ? held.map((r) => (r.key === run.key ? run : r))
        : [run, ...held],
    );
  }, []);
  const value = useMemo(() => ({ runs, record }), [runs, record]);
  return <RunActivityContext.Provider value={value}>{children}</RunActivityContext.Provider>;
}

export function useRunActivity(): RunActivity {
  return useContext(RunActivityContext);
}
