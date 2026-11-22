/**
 * One conversation turn's run, drawn live from its AG-UI stream (#69, #949; docs/specs/app.md,
 * "Run events to the browser").
 *
 * `stream` sends the turn to its stream route through the run transport, folds each event into
 * the run's state with the reducer, says its progress through the announcer, and records it in
 * the tab's activity log. It settles with the state once the stream has closed: a stream that
 * closes, or drops, before the run ended leaves the run interrupted, with no finish invented. A
 * turn refused before its stream opened sent no event; `stream` then rejects with the error the
 * JSON route would have raised (`streamFailure`), so the page says why as it did before.
 *
 * `cancel` asks the server to cancel the run and reads on until the stream says it was.
 */

import { useCallback } from "react";

import { streamFailure } from "../../conversation/api";
import { useSessionRef, useSessionState } from "../../conversation/session";
import { useRunActivity } from "../../run/activity";
import { initialRunState, reduce, type RunState, streamEnded } from "../../run/reduce";
import { streamRun, useRunTransport } from "../../run/transport";
import { useRunAnnouncements } from "../run/useRunAnnouncements";

export interface TurnStream {
  /** The run being streamed, or the last one until `clear`; null when there is none. */
  run: RunState | null;
  /** Cancel has been asked for and the stream has not yet said the run was cancelled. */
  cancelling: boolean;
  /** Streams one turn of `conversationId`, whose body is `forwardedProps`. */
  stream(conversationId: string, forwardedProps: Record<string, unknown>): Promise<RunState>;
  /** Asks for the run being streamed to be cancelled; nothing if none is. */
  cancel(): void;
  /** Lets the last run go. */
  clear(): void;
}

export function useTurnStream(): TurnStream {
  const transport = useRunTransport();
  const { record } = useRunActivity();
  // Kept in the conversation session, so that a run goes on being drawn, and can be cancelled,
  // after the page is left and drawn again.
  const [run, setRun] = useSessionState<RunState | null>("turn.run", null);
  const [cancelling, setCancelling] = useSessionState("turn.cancelling", false);
  const streamingRef = useSessionRef<{ conversationId: string; runId: string } | null>(
    "turn.streaming",
    null,
  );
  // A new run starts idle, so that nothing said of the last one counts as said of this one.
  useRunAnnouncements(run ?? initialRunState);

  const stream = useCallback(
    async (conversationId: string, forwardedProps: Record<string, unknown>) => {
      const runId = crypto.randomUUID();
      const startedAt = new Date().toISOString();
      streamingRef.current = { conversationId, runId };
      setCancelling(false);
      setRun(initialRunState);
      let state = initialRunState;
      let seen = false;
      const show = (next: RunState) => {
        state = next;
        setRun(next);
        record({ key: runId, conversationId, startedAt, state: next });
      };
      const agent = transport.agentFor(conversationId);
      try {
        await streamRun(agent, { runId, forwardedProps }, (event) => {
          seen = true;
          show(reduce(state, event));
        }).done;
      } catch (error) {
        if (!seen) {
          streamingRef.current = null;
          setRun(null);
          throw streamFailure(error);
        }
      }
      streamingRef.current = null;
      setCancelling(false);
      show(streamEnded(state));
      return state;
    },
    [transport, record, setRun, setCancelling, streamingRef],
  );

  const cancel = useCallback(() => {
    const open = streamingRef.current;
    if (!open) return;
    setCancelling(true);
    transport.cancel(open.conversationId, open.runId).catch(() => setCancelling(false));
  }, [transport, setCancelling, streamingRef]);

  const clear = useCallback(() => {
    setRun(null);
    setCancelling(false);
  }, [setRun, setCancelling]);

  return { run, cancelling, stream, cancel, clear };
}
