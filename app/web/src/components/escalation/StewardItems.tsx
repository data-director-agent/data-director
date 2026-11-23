/**
 * What happened with the project's data stewards between two turns of the conversation, each as
 * an item of the transcript: a steward's message, marked plainly as from a named person and a data
 * steward, never as an agent, and each move in a request as a marker with its note
 * (docs/specs/stewardship.md, invariant 10).
 */

import { LifeBuoy } from "lucide-react";
import { useMemo } from "react";

import { useSteward } from "./StewardContext";
import { type StewardEvent, eventsBetween, stewardEvents } from "./events";
import { formatDateTime } from "../../format";
import { MOVE_SAID } from "./wording";

/** The steward events after `from` and at or before `to` (or since `from`, with no `to`). */
export function StewardItems({ from, to }: { from: string; to: string | null }) {
  const steward = useSteward();
  const events = useMemo(
    () => stewardEvents(steward?.escalations?.escalations ?? [], steward?.stewarding?.messages ?? []),
    [steward?.escalations, steward?.stewarding],
  );
  return eventsBetween(events, from, to).map((event) => <StewardItem key={event.key} event={event} />);
}

function StewardItem({ event }: { event: StewardEvent }) {
  const when = <time dateTime={event.at}>{formatDateTime(event.at, { dateStyle: "medium", timeStyle: "short" })}</time>;
  if (!event.fromSteward) {
    const said = event.kind === "open" ? `sent this to ${event.team ?? "the data stewards"}` : MOVE_SAID[event.kind];
    return (
      <li className="turn steward-marker">
        <p className="hint">
          <LifeBuoy size="1em" aria-hidden="true" /> {event.by.name} {said ?? event.kind}, {when}
          {event.note && event.kind !== "open" ? `: ${event.note}` : ""}
        </p>
      </li>
    );
  }
  return (
    <li className="turn steward-turn">
      <div className="turn-agent">
        <p className="turn-speaker">
          <strong className="turn-speaker-name">
            <span className="person-icon" aria-hidden="true">
              <LifeBuoy size="1.125em" />
            </span>
            Data steward: {event.by.name}
          </strong>{" "}
          <span className="hint">
            {event.kind === "message" ? "" : `${MOVE_SAID[event.kind] ?? event.kind}, `}
            {when}
          </span>
        </p>
        {event.note && <p>{event.note}</p>}
      </div>
    </li>
  );
}
