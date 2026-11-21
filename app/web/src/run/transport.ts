/**
 * Where a conversation turn's AG-UI stream comes from, behind one interface so that tests and
 * fixtures can stand in for the server (docs/specs/app.md, "Run events to the browser").
 *
 * A live turn is an `HttpAgent` posting to the turn's stream route, which takes a `RunAgentInput`
 * whose `forwardedProps` is the turn's body; a replayed one is a `CassetteAgent`. Both are
 * `AbstractAgent`s, and the shell reads either through `streamRun` in the same way.
 *
 * `streamRun` reads the agent's raw events (`agent.run`), not `runAgent`: the run reducer is what
 * checks them (`reduce.ts`), keeping an unrecognised or malformed event as such instead of failing
 * the run. `runAgent`'s own checks are stricter than the harness's binding, which ends a cancelled
 * run with the stopped stage still open, TODO(#1007).
 *
 * Cancelling a turn asks the server to cancel its run; the stream is read on until it ends with
 * the cancelled `RUN_FINISHED`, so the run view says what the run came to rather than guessing.
 */

import { HttpAgent, type AbstractAgent, type BaseEvent, type RunAgentInput } from "@ag-ui/client";
import { createContext, useContext } from "react";

import { CassetteAgent } from "./cassette";
import { serverAnswered } from "../status";

/** The route that cancels the turn whose AG-UI run is `runId`. */
export function turnCancelUrl(conversationId: string, runId: string): string {
  return `/api/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(runId)}/cancel`;
}

/** The route that streams a turn of the conversation `conversationId`. */
export function turnStreamUrl(conversationId: string): string {
  return `/api/conversations/${encodeURIComponent(conversationId)}/turns/stream`;
}

export interface RunTransport {
  /** An agent for one turn of the conversation `conversationId`, its AG-UI thread. */
  agentFor(conversationId: string): AbstractAgent;
  /** Asks for the turn `runId` of the conversation `conversationId` to be cancelled. Its stream
   * then ends with a cancelled `RUN_FINISHED`; a turn that has already ended is left as it is. */
  cancel(conversationId: string, runId: string): Promise<void>;
}

/** Live turns, streamed from the server. */
export const httpTransport: RunTransport = {
  agentFor(conversationId) {
    return new HttpAgent({ url: turnStreamUrl(conversationId), threadId: conversationId });
  },
  async cancel(conversationId, runId) {
    const response = await fetch(turnCancelUrl(conversationId, runId), { method: "POST" });
    // 404: the turn is no longer streaming, so it has ended, and its stream says how.
    if (!response.ok && response.status !== 404) {
      throw new Error(serverAnswered(response.status));
    }
  },
};

/** Turns replayed from a cassette's events, `paceMs` apart (0, the default, all at once). */
export function cassetteTransport(
  events: readonly unknown[],
  { paceMs = 0 }: { paceMs?: number } = {},
): RunTransport {
  const replaying = new Map<string, CassetteAgent>();
  return {
    agentFor(conversationId) {
      const agent = new CassetteAgent({ events, paceMs, threadId: conversationId });
      replaying.set(conversationId, agent);
      return agent;
    },
    cancel(conversationId) {
      replaying.get(conversationId)?.cancel();
      return Promise.resolve();
    },
  };
}

/** What a turn sends: its AG-UI `runId`, and the turn's body as `forwardedProps`. */
export interface TurnRequest {
  runId: string;
  forwardedProps: Record<string, unknown>;
}

export interface StreamingRun {
  /** Settles when the stream ends: resolved when it completes, rejected if it fails (a refusal
   * before the stream opened, or a dropped connection). */
  done: Promise<void>;
  /** Stops reading; for a live turn, closes the connection. */
  stop(): void;
}

/** Streams one run of `agent`, giving each event, as sent, to `onEvent`. */
export function streamRun(
  agent: AbstractAgent,
  { runId, forwardedProps }: TurnRequest,
  onEvent: (event: BaseEvent) => void,
): StreamingRun {
  const input: RunAgentInput = {
    threadId: agent.threadId,
    runId,
    messages: [],
    tools: [],
    context: [],
    state: {},
    forwardedProps,
  };
  let stop = () => {};
  const done = new Promise<void>((resolve, reject) => {
    const subscription = agent.run(input).subscribe({
      next: onEvent,
      error: (error: unknown) => reject(error instanceof Error ? error : new Error(String(error))),
      complete: resolve,
    });
    stop = () => {
      subscription.unsubscribe();
      resolve();
    };
  });
  return { done, stop: () => stop() };
}

export const RunTransportContext = createContext<RunTransport>(httpTransport);

export function useRunTransport(): RunTransport {
  return useContext(RunTransportContext);
}
