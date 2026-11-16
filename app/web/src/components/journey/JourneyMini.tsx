/**
 * A project's journey at a glance, for a project card: six segments, each filled as far as its
 * phase's steps are done or skipped, with the phase of the suggested step outlined. It links to
 * the full map and says the same in words for a screen reader.
 */

import "./JourneyMap.css";

import { type Line, locate } from "../../flow/journey";
import type { ProcessFlow, ProjectProgress } from "../../flow/types";
import { Link, journeyPath } from "../../route";

export function journeyWords(lines: Line[], flow: ProcessFlow, progress: ProjectProgress): string {
  const counted = lines.reduce((n, l) => n + l.counted, 0);
  const finished = lines.reduce((n, l) => n + l.finished, 0);
  const next = locate(flow, progress.suggested);
  return (
    `${finished} of ${counted} steps done or skipped` +
    (next ? `; suggested next: ${next.step.label}, in phase ${next.phase.number}` : "")
  );
}

export function JourneyMini({
  projectId,
  lines,
  flow,
  progress,
}: {
  projectId: string;
  lines: Line[];
  flow: ProcessFlow;
  progress: ProjectProgress;
}) {
  const next = locate(flow, progress.suggested);
  const words = journeyWords(lines, flow, progress);
  return (
    <Link to={journeyPath(projectId)} className="journey-mini-link" aria-label={`Journey map: ${words}`}>
      <ol className="journey-mini" aria-hidden="true">
        {lines.map((line) => (
          <li
            key={line.phase.number}
            className={
              next?.phase.number === line.phase.number
                ? "journey-mini-segment is-next"
                : "journey-mini-segment"
            }
          >
            <span
              className="journey-mini-fill"
              style={{ width: `${line.counted ? (100 * line.finished) / line.counted : 0}%` }}
            />
          </li>
        ))}
      </ol>
      <span className="journey-mini-words muted">{words}</span>
    </Link>
  );
}
