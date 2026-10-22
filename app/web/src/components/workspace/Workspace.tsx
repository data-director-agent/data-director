/**
 * The workspace around the researcher's task: where the work stands across the top, the
 * Blueprint's phases on the left, the conversation in the centre, the open run and its evidence
 * on the right, and the activity log beneath. When proposals and the review gate exist
 * (#71-#73) they take the centre and the conversation docks.
 *
 * The source order is the reading order at every width; only the columns change (`base.css`).
 * On a narrow screen an open run is its own view, so the rest is hidden until it is closed.
 */

import type { ReactNode } from "react";

export function Workspace({
  heading,
  status,
  phases,
  centre,
  context,
  log,
  runOpen,
}: {
  heading: ReactNode;
  status: ReactNode;
  phases: ReactNode;
  centre: ReactNode;
  context: ReactNode;
  log: ReactNode;
  runOpen: boolean;
}) {
  return (
    <div className={`workspace${runOpen ? " has-run" : ""}`}>
      <div className="workspace-head">
        {heading}
        {status}
      </div>
      {phases}
      <div className="workspace-centre">{centre}</div>
      {context}
      {log}
    </div>
  );
}
