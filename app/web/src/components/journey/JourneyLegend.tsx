/**
 * The key to the journey map's marks (docs/specs/app.md, "The journey map"), at the foot of the
 * page. Each swatch reuses the map's own classes, so it cannot drift from what a stop looks like;
 * the marks are decoration and every one is also said in words, here and on the stops.
 */

import { MapPin } from "lucide-react";

import { STATE_WORDS } from "./JourneyMap";

interface Mark {
  /** The classes of the stop the swatch is drawn as. */
  classes: string;
  label: string;
  meaning: string;
  /** The marks that are not a stop's own look are drawn by the caller. */
  struck?: boolean;
}

const MARKS: Mark[] = [
  {
    classes: "is-open",
    label: STATE_WORDS.open,
    meaning: "An empty circle: nothing here yet.",
  },
  {
    classes: "is-started",
    label: STATE_WORDS.started,
    meaning: "A half-filled circle: under way.",
  },
  {
    classes: "is-done",
    label: STATE_WORDS.done,
    meaning: "A filled circle: finished.",
  },
  {
    classes: "is-skipped",
    label: STATE_WORDS.skipped,
    meaning: "A grey circle and a struck-through name: you chose to pass over it.",
    struck: true,
  },
  {
    classes: "is-open is-optional",
    label: "Optional",
    meaning: "A dashed outline: worth doing, but you can leave it out.",
  },
  {
    classes: "is-open is-out-of-scope",
    label: "Not in this version",
    meaning: "A dotted outline: Data Director does not yet help with this step.",
  },
  {
    classes: "is-open is-suggested",
    label: "Suggested next",
    meaning: "A ringed circle: the step Data Director suggests doing next.",
  },
  {
    classes: "is-open is-waiting",
    label: "Waiting on you",
    meaning: "An amber outline: a document or question needs your decision.",
  },
];

export function JourneyLegend() {
  return (
    <section className="journey-legend" aria-labelledby="journey-legend-title">
      <h2 id="journey-legend-title" className="journey-legend-title">
        How to read the map
      </h2>
      <ul className="journey-legend-list">
        {MARKS.map((mark) => (
          <li key={mark.label} className={`journey-station ${mark.classes} journey-legend-item`}>
            <span className="journey-dot" aria-hidden="true" />
            <span className="journey-stop-text">
              <span
                className={
                  mark.struck ? "journey-legend-label journey-stop-label" : "journey-legend-label"
                }
              >
                {mark.label}
              </span>
              <span className="journey-stop-state">{mark.meaning}</span>
            </span>
          </li>
        ))}
        <li className="journey-legend-item">
          <span className="journey-diamond" aria-hidden="true" />
          <span className="journey-stop-text">
            <span className="journey-legend-label">Decision</span>
            <span className="journey-stop-state">
              A dashed diamond: a question from the setup that can skip the steps after it.
            </span>
          </span>
        </li>
        <li className="journey-legend-item is-entry">
          <MapPin size="1em" aria-hidden="true" className="journey-entry-icon" />
          <span className="journey-stop-text">
            <span className="journey-legend-label">Where you started</span>
            <span className="journey-stop-state">
              A green pin: the point in the journey this project joined at. Steps before it are
              greyed.
            </span>
          </span>
        </li>
      </ul>
    </section>
  );
}
