/**
 * Replaying a recorded AG-UI stream (docs/specs/transport.md): a cassette in `app/web/cassettes`
 * is what the harness's binding streamed for one kind of run, one event a line
 * (`app/tests/test_ui_cassettes.py` records them).
 *
 * `CassetteAgent` is an `AbstractAgent`, as `HttpAgent` is, so a replayed run goes through the same
 * client pipeline (`runAgent`, its event checks and its subscribers) as a live one. The cassette is
 * replayed as recorded: its `threadId` and `runId` are not rewritten.
 */

import { AbstractAgent, type AgentConfig, type BaseEvent, type RunAgentInput } from "@ag-ui/client";
import { Observable } from "rxjs";

/** A cassette's events, one JSON object a line; blank lines are skipped. */
export function parseCassette(text: string): unknown[] {
  return text
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => JSON.parse(line) as unknown);
}

export interface CassetteAgentConfig extends AgentConfig {
  /** The events to replay, in order, as `parseCassette` gives them. */
  events: readonly unknown[];
  /** Milliseconds between one event and the next; 0, the default, replays them all at once. */
  paceMs?: number;
}

/** An agent that replays a cassette instead of calling the server. */
export class CassetteAgent extends AbstractAgent {
  readonly events: readonly unknown[];
  readonly paceMs: number;

  constructor({ events, paceMs = 0, ...config }: CassetteAgentConfig) {
    super(config);
    this.events = events;
    this.paceMs = paceMs;
  }

  // The input is not read: what a recorded run streamed does not depend on what is sent now.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  run(_input: RunAgentInput): Observable<BaseEvent> {
    const events = this.events as readonly BaseEvent[];
    const paceMs = this.paceMs;
    return new Observable<BaseEvent>((subscriber) => {
      if (paceMs <= 0) {
        for (const event of events) subscriber.next(event);
        subscriber.complete();
        return undefined;
      }
      let next = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const emit = () => {
        const event = events[next];
        if (event === undefined) {
          subscriber.complete();
          return;
        }
        subscriber.next(event);
        next += 1;
        timer = setTimeout(emit, paceMs);
      };
      emit();
      // Unsubscribing (`abortRun`) stops the replay.
      return () => clearTimeout(timer);
    });
  }

  clone(): CassetteAgent {
    return new CassetteAgent({
      events: this.events,
      paceMs: this.paceMs,
      ...(this.agentId === undefined ? {} : { agentId: this.agentId }),
      description: this.description,
      threadId: this.threadId,
    });
  }
}
