/**
 * A project's journey drawn as a map (docs/specs/app.md, "The journey map"), after the Blueprint's
 * §8 figures: each phase a line of stops, the entry points pinned to the phases they join at, the
 * intake's decision points as diamonds before the steps they can skip, a band across the whole
 * saying every action is recorded, and the last phase looping back rather than ending.
 *
 * Every stop is a real button in an ordered list, so the map reads in order with a keyboard or a
 * screen reader and reflows at any zoom; the lines and dots are decoration drawn in CSS, and each
 * state is also said in words. It names no agent and no requirement, and computes no state: the
 * lines come from `journey` (flow/journey.ts).
 */

import "./JourneyMap.css";

import { MapPin, Repeat } from "lucide-react";

import type { Line, Station, StationState } from "../../flow/journey";
import { Link } from "../../route";
import { ToggleButton } from "../ui/Button";

export const STATE_WORDS: Record<StationState, string> = {
  done: "Done",
  started: "Started",
  skipped: "Skipped",
  open: "Not started",
};

/** A step's state in words. A step out of scope says so, unless the intake skipped it as the
 * branch of a decision not taken (dd_sdk.intake), when it says it is skipped. */
export function stateWords(step: Station["step"], state: StationState): string {
  if (!step.out_of_scope) return STATE_WORDS[state];
  return state === "skipped" ? "Skipped, not in this version" : "Not in this version";
}

/** The stop's state classes: an out-of-scope step keeps its own look, and is struck through when
 * skipped. */
function stateClasses(step: Station["step"], state: StationState): string {
  if (!step.out_of_scope) return `is-${state}`;
  return state === "skipped" ? "is-out-of-scope is-skipped" : "is-out-of-scope";
}

/** The stop's state, and what else is true of it, as one phrase for its accessible name. */
export function stationSummary(station: Station): string {
  const parts = [stateWords(station.step, station.state)];
  if (station.step.optional) parts.push("optional");
  if (station.suggested) parts.push("suggested next");
  if (station.waiting) parts.push("waiting on you");
  return parts.join(", ");
}

/** The element id of a stop's button, so focus can return to it. */
export function stopId(stepId: string): string {
  return `journey-stop-${stepId.replaceAll(".", "-")}`;
}

export function JourneyMap({
  lines,
  entry,
  entryByModel = false,
  selected,
  onSelect,
  waitingOnly = false,
}: {
  lines: Line[];
  /** The entry point the project started at, if one is recorded. */
  entry: number | null;
  entryByModel?: boolean;
  /** The step whose details are open. */
  selected: string | null;
  onSelect(stepId: string | null): void;
  /** Dim every stop that does not wait on the researcher. */
  waitingOnly?: boolean;
}) {
  return (
    <div className={waitingOnly ? "journey journey-waiting-only" : "journey"}>
      <p className="journey-rail">
        Everything Data Director does in this project is recorded, so it can be checked later.{" "}
        <Link to="/activity">See the activity</Link>
      </p>
      <ol className="journey-lines" aria-label="The phases in order">
        {lines.map((line) => {
          const headingId = `journey-phase-${line.phase.number}`;
          return (
            <li key={line.phase.number} className="journey-line">
              <h2 id={headingId} className="journey-phase">
                <span className="journey-phase-number">Phase {line.phase.number}</span>{" "}
                {line.phase.name}
              </h2>
              <p className="journey-phase-summary muted">{line.phase.summary}</p>
              <p className="journey-count">
                {line.finished} of {line.counted} done or skipped
              </p>
              {line.entries.map((e) => {
                const yours = e.number === entry;
                return (
                  <p key={e.number} className={yours ? "journey-entry is-yours" : "journey-entry"}>
                    <MapPin size="1em" aria-hidden="true" className="journey-entry-icon" />
                    <span>
                      {yours ? "You started here: " : "Start here if: "}
                      {e.text}
                      {yours && entryByModel && (
                        <span className="muted"> (set by Data Director from what you said)</span>
                      )}
                    </span>
                  </p>
                );
              })}
              <ol className="journey-stops" aria-labelledby={headingId}>
                {line.items.map((item) =>
                  item.kind === "decision" ? (
                    <li
                      key={item.decision.question_id}
                      className={item.waiting ? "journey-decision is-waiting" : "journey-decision"}
                    >
                      <span className="journey-diamond" aria-hidden="true" />
                      <span className="journey-decision-text">
                        <span className="visually-hidden">Decision: </span>
                        {item.decision.prompt}{" "}
                        <span className="journey-decision-answer">
                          {item.decision.answer_labels?.length
                            ? `You said: ${item.decision.answer_labels.join(", ")}`
                            : item.decision.asked
                              ? "Not answered yet"
                              : "Not asked from where you started"}
                        </span>
                        {item.waiting && (
                          <span className="status status-warn journey-badge">Waiting on you</span>
                        )}
                      </span>
                    </li>
                  ) : (
                    <li
                      key={item.step.id}
                      className={[
                        "journey-station",
                        stateClasses(item.step, item.state),
                        item.step.optional && "is-optional",
                        item.suggested && "is-suggested",
                        item.waiting && "is-waiting",
                        item.beforeEntry && "is-before-entry",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      <ToggleButton
                        id={stopId(item.step.id)}
                        variant="quiet"
                        className="journey-stop"
                        isSelected={selected === item.step.id}
                        onChange={(on) => onSelect(on ? item.step.id : null)}
                        aria-label={`${item.step.label}: ${stationSummary(item)}`}
                      >
                        <span className="journey-dot" aria-hidden="true" />
                        <span className="journey-stop-text" aria-hidden="true">
                          <span className="journey-stop-label">{item.step.label}</span>
                          <span className="journey-stop-state">{stationSummary(item)}</span>
                        </span>
                      </ToggleButton>
                    </li>
                  ),
                )}
              </ol>
            </li>
          );
        })}
      </ol>
      <p className="journey-loop">
        <Repeat size="1em" aria-hidden="true" /> After publishing, the journey loops: keep improving
        your data's description and linking it to new work for as long as it is used.
      </p>
    </div>
  );
}
