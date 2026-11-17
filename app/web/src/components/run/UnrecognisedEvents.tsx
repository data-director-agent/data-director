/**
 * The events of a run the shell could not draw: those of a type or `CUSTOM` name it does not know,
 * in one collapsed group, and those it could not read, as an error (#69). Neither stops the run.
 */

import "./UnrecognisedEvents.css";

import type { RunState } from "../../run/reduce";

export function UnrecognisedEvents({ run }: { run: RunState }) {
  const { count, types } = run.unrecognised;
  return (
    <>
      {run.malformed > 0 && (
        <div className="callout status-danger">
          <p>
            <strong>Malformed event from server</strong>
          </p>
          <p>
            {run.malformed === 1
              ? "One update from the run could not be read."
              : `${run.malformed} updates from the run could not be read.`}{" "}
            The run carried on without them.
          </p>
        </div>
      )}
      {count > 0 && (
        <details className="unrecognised-events">
          <summary>Unrecognised events ({count})</summary>
          <p className="muted">
            The run sent updates this page does not know how to show. They are not needed to follow
            the run.
          </p>
          <ul>
            {types.map((type) => (
              <li key={type}>
                <code>{type}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
