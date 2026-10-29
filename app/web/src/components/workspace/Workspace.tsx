/**
 * The workspace around the researcher's task: where the work stands across the top, the
 * Blueprint's phases on the left, the conversation in the centre, the project's documents and
 * the orchestrator's limits on the right, and the activity log beneath. A delegated run opens
 * inside the conversation. When proposals and the review gate exist (#71-#73) they take the
 * centre and the conversation docks.
 *
 * The source order is the reading order at every width; only the columns change (`layout.css`).
 */

import type { ReactNode } from "react";

import { PageHeader } from "../frame/PageHeader";

export function Workspace({
  title,
  titleHidden,
  status,
  phases,
  centre,
  context,
  log,
}: {
  title: string;
  titleHidden?: boolean | undefined;
  status: ReactNode;
  phases: ReactNode;
  centre: ReactNode;
  context: ReactNode;
  log: ReactNode;
}) {
  return (
    <div className="workspace">
      <PageHeader title={title} titleHidden={titleHidden} className="workspace-head">
        {status}
      </PageHeader>
      {phases}
      <div className="workspace-centre">{centre}</div>
      {context}
      {log}
    </div>
  );
}
