/**
 * A project's steward events in time order: each move in an escalation's history and each
 * message a steward wrote in the project, as the conversation shows them between its turns.
 * Steward messages are the project's, not one conversation's, so the shell places each between
 * the turns it fell between (docs/specs/stewardship.md, invariant 10).
 */

import type { Principal } from "../../api/contract";
import type { Escalation, StewardMessage } from "../../project/escalations";
import { moveSaid, moveTarget } from "./wording";

export interface StewardEvent {
  /** Unique within the project, and the same on every read. */
  key: string;
  at: string;
  by: Principal;
  /** Made by a steward, as a steward, not by a member of the project. */
  fromSteward: boolean;
  /** The move in an escalation, or "message" for a steward's message in the project. */
  kind: string;
  note: string | null;
  /** The escalation's team, for a move. */
  team: string | null;
  /** The colleague or team a reassignment or transfer passed it to. */
  target: string | null;
}

export function stewardEvents(
  escalations: readonly Escalation[],
  messages: readonly StewardMessage[],
): StewardEvent[] {
  const moves = escalations.flatMap((e) =>
    e.history.map((m, index) => ({
      key: `${e.escalation_id}:${index}`,
      at: m.at,
      by: m.by,
      fromSteward: m.acting_as === "steward",
      kind: m.move,
      note: m.note ?? null,
      team: e.team_name,
      target: moveTarget(m),
    })),
  );
  const said = messages.map((m, index) => ({
    key: `message:${index}:${m.at}`,
    at: m.at,
    by: m.by,
    fromSteward: true,
    kind: "message",
    note: m.note,
    team: null,
    target: null,
  }));
  return [...moves, ...said].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
}

/** The events after `from` and at or before `to` (or since `from`, with no `to`). */
export function eventsBetween(events: readonly StewardEvent[], from: string, to: string | null): StewardEvent[] {
  const after = Date.parse(from);
  const until = to === null ? Infinity : Date.parse(to);
  return events.filter((e) => {
    const at = Date.parse(e.at);
    return at > after && at <= until;
  });
}

/** The event in a sentence, as it is announced. */
export function eventSaid(event: StewardEvent): string {
  if (event.kind === "message") return `Data steward ${event.by.name} wrote: ${event.note ?? ""}`;
  return `Data steward ${event.by.name} ${moveSaid(event.kind, event.target)}.`;
}
