/**
 * The workspace around the researcher's task: a strip across the top
 * showing the Blueprint's phases, which opens for detail. Beneath that, three columns: the
 * person's conversations on the left, the open conversation in the centre, and an overview of
 * the project on the right (its current state, attached files and documents). A delegated run
 * opens inside the conversation. The activity log is a page of its own. When proposals and the
 * review gate exist (#71-#73) they take the centre and the conversation docks.
 *
 * The source order is the reading order at every width; only the columns change (`layout.css`).
 */

import type { ReactNode } from "react";

import { PageHeader } from "../frame/PageHeader";

export function Workspace({
  title,
  titleHidden,
  phases,
  history,
  centre,
  context,
}: {
  title: string;
  titleHidden?: boolean | undefined;
  phases: ReactNode;
  history?: ReactNode;
  centre: ReactNode;
  context: ReactNode;
}) {
  return (
    <div className="workspace">
      <PageHeader title={title} titleHidden={titleHidden} className="workspace-head" />
      {phases}
      {history}
      <div className="workspace-centre">{centre}</div>
      {context}
    </div>
  );
}
