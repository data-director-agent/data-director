/**
 * How many checks the report met of those it assessed, one row for each of F, A, I and R: a meter
 * with its count in words beside it, so that neither the bar nor its colour carries the meaning
 * alone. A principle with nothing a draft can meet says so rather than drawing an empty bar.
 */

import { CircleCheck, CircleDashed, Lock } from "lucide-react";

import {
  type FairnessReport,
  PRINCIPLES,
  type Tally,
  tallyOf,
} from "../../project/fairness";

function state(tally: Tally): { word: string; Icon: typeof CircleCheck } {
  if (tally.assessed === 0) return { word: "Checked at deposit", Icon: Lock };
  if (tally.met === tally.assessed)
    return { word: "All met", Icon: CircleCheck };
  return { word: `${tally.assessed - tally.met} to do`, Icon: CircleDashed };
}

export function PrincipleMeters({
  report,
  previous = null,
}: {
  report: FairnessReport;
  /** The report before, to say where a count has gone up. */
  previous?: FairnessReport | null;
}) {
  return (
    <ul className="fair-meters">
      {PRINCIPLES.map(({ id, name }) => {
        const tally = tallyOf(report, id);
        const before = previous ? tallyOf(previous, id) : null;
        const { word, Icon } = state(tally);
        const label =
          tally.assessed === 0
            ? `${name}: no check a draft can meet; checked at deposit`
            : `${name}: ${tally.met} of ${tally.assessed} checks met`;
        return (
          <li
            key={id}
            className={
              tally.assessed > 0 && tally.met === tally.assessed
                ? "fair-met"
                : undefined
            }
          >
            <span className="fair-meter-name">
              <abbr title={name} aria-hidden="true">
                {id}
              </abbr>{" "}
              {name}
            </span>
            {tally.assessed > 0 ? (
              <meter
                min={0}
                max={tally.assessed}
                value={tally.met}
                aria-label={label}
              />
            ) : (
              <span className="fair-meter-none" aria-hidden="true" />
            )}
            <span className="fair-meter-count">
              {tally.assessed > 0 ? `${tally.met} of ${tally.assessed}` : "—"}
            </span>
            <span className="fair-meter-state">
              <Icon size="1em" aria-hidden="true" /> {word}
              {before && before.met < tally.met && (
                <span className="fair-gain">, up from {before.met}</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
