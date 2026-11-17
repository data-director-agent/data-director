/**
 * A stand-in for a conversation turn's stream (`run/transport.ts`), for the shell's tests: each
 * turn sent is given to `sent` with its conversation and body (the stream's `forwardedProps`), and
 * the run streams what `sent` gives back: by default the events of the succeeded cassette, which
 * the harness's binding recorded. A `sent` that rejects is a turn refused before its stream
 * opened, as `HttpAgent` reports one.
 */

import { AbstractAgent, type BaseEvent, type RunAgentInput } from "@ag-ui/client";
import { Observable } from "rxjs";

import cancelledText from "../../cassettes/cancelled.jsonl?raw";
import succeededText from "../../cassettes/succeeded.jsonl?raw";
import { parseCassette } from "../run/cassette";
import type { RunTransport } from "../run/transport";

/** The events of a run that succeeded, and of one that was cancelled at the agent stage. */
export const SUCCEEDED = parseCassette(succeededText);
export const CANCELLED = parseCassette(cancelledText);

/** Takes one turn: the events its run streams, or anything but a list for `SUCCEEDED`. */
export type TurnSent = (conversationId: string, body: Record<string, unknown>) => Promise<unknown>;

class TurnAgent extends AbstractAgent {
  constructor(
    private readonly sent: TurnSent,
    threadId: string,
  ) {
    super({ threadId });
  }

  run(input: RunAgentInput): Observable<BaseEvent> {
    return new Observable<BaseEvent>((subscriber) => {
      const body = (input.forwardedProps ?? {}) as Record<string, unknown>;
      this.sent(this.threadId, body).then(
        (events) => {
          const streamed = Array.isArray(events) ? (events as unknown[]) : SUCCEEDED;
          for (const event of streamed) subscriber.next(event as BaseEvent);
          subscriber.complete();
        },
        (error: unknown) => subscriber.error(error),
      );
    });
  }

  clone(): TurnAgent {
    return new TurnAgent(this.sent, this.threadId);
  }
}

/** A transport whose turns go to `sent`; its `cancel` does nothing but is recorded. */
export function turnTransport(sent: TurnSent = () => Promise.resolve()): RunTransport {
  return {
    agentFor: (conversationId) => new TurnAgent(sent, conversationId),
    cancel: vi.fn(() => Promise.resolve()),
  };
}
