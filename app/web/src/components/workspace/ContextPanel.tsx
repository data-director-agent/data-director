/**
 * Beside the conversation, what a person needs from the project while they talk to Data Director
 * (docs/specs/app.md). It does not summarise the project: the project's pages show it in full.
 * From the top:
 *
 * - what waits on the person, each with the one thing to do about it;
 * - where the project stands, in one line, and the step suggested next;
 * - how FAIR its metadata record is so far, where an agent here gives FAIR feedback;
 * - what Data Director is working from: the facts that shape its answers and the repository chosen;
 * - the files and documents, this conversation's first;
 * - the guardrails, closed until opened.
 *
 * Deciding stays on the project's pages; a button here either goes there or puts a question in
 * the message box, unsent. A delegated run and its evidence open in the transcript, beside the
 * turn they support.
 */

import "./ContextPanel.css";

import type { Conversation } from "../../conversation/types";
import type { ProjectProgress } from "../../flow/types";
import type { ProjectSummary } from "../../project/api";
import type { DocumentsRead } from "../../project/drafted";
import type { FlowLoad } from "./PhaseTracker";
import { useProjectFacts } from "./project-pane/facts";
import { FairFeedback } from "./project-pane/FairFeedback";
import { FilesAndDocuments } from "./project-pane/FilesAndDocuments";
import { Guardrails } from "./project-pane/Guardrails";
import { WaitingOnYou } from "./project-pane/WaitingOnYou";
import { WhereWeAre } from "./project-pane/WhereWeAre";
import { WorkingFrom } from "./project-pane/WorkingFrom";

export function ContextPanel({
  projectId = null,
  project = null,
  conversation = null,
  documents = { state: "loading" },
  flow = { state: "loading" },
  progress,
  fairFeedback = false,
  refresh,
  onAsk,
  onInventorySaved,
}: {
  /** The project the workspace is in, or null before the first message starts one. */
  projectId?: string | null;
  /** What the projects list says of it, once it lists it. */
  project?: ProjectSummary | null;
  conversation?: Conversation | null;
  /** The project's documents, as the workspace last read them. */
  documents?: DocumentsRead;
  /** The process flow, once read, and where the project is in it. */
  flow?: FlowLoad;
  progress?: ProjectProgress | undefined;
  /** Whether an agent in this deployment returns FAIR reports, so that feedback can be asked for. */
  fairFeedback?: boolean;
  /** Changes when a turn settles, so that what the pane reads itself is read again. */
  refresh?: unknown;
  /** Puts `text` in the message box, unsent, for the person to send or change. */
  onAsk?: ((text: string) => void) | undefined;
  /** Called once a revised inventory is saved, so that what reads the project reads it again. */
  onInventorySaved?: (() => void) | undefined;
}) {
  const facts = useProjectFacts(projectId, refresh);
  return (
    <section aria-labelledby="context-heading" className="workspace-context project-pane">
      {/* The workspace header names the project and links to its details, so this does not. */}
      <h2 id="context-heading">Project</h2>
      {!projectId ? (
        <p>
          Your first message starts a new project, which keeps the inventory you attach, the facts
          you confirm and the documents agents draft for you.
        </p>
      ) : (
        <>
          <WaitingOnYou
            projectId={projectId}
            project={project}
            documents={documents.state === "loaded" ? documents.documents : []}
            facts={facts}
            onAsk={onAsk}
          />
          <WhereWeAre
            projectId={projectId}
            flow={flow.state === "loaded" ? flow.flow : null}
            progress={progress ?? null}
            onAsk={onAsk}
          />
          {fairFeedback && (
            <FairFeedback
              projectId={projectId}
              documents={documents.state === "loaded" ? documents.documents : []}
              refresh={refresh}
              onAsk={onAsk}
            />
          )}
          <WorkingFrom projectId={projectId} repository={project?.repository} facts={facts} />
          <FilesAndDocuments
            projectId={projectId}
            // The open conversation was read after the projects list, so it knows of a newer inventory.
            inventory={conversation ? conversation.inventory : project?.inventory}
            documents={documents}
            conversation={conversation}
            onInventorySaved={onInventorySaved}
          />
        </>
      )}
      <Guardrails />
    </section>
  );
}
