/**
 * Beside the conversation, an overview of the project it was started in (docs/specs/app.md):
 * where the project stands, the files attached to it (the inventory it holds) and the documents
 * agents have drafted in it, each with its latest version's state and a link to review it. Where it stands, its dataset, phase, repository and open
 * governance flags, needs a record of the project (#160), so each is drawn as not built, linked
 * to its issues, with no value standing in for it. A delegated run and its evidence open in the
 * transcript, beside the turn they support.
 */

import "./ContextPanel.css";

import { useMemo } from "react";

import { INVENTORY_GUIDE, type InventorySource } from "../../conversation/inventory";
import type { Conversation } from "../../conversation/types";
import { useProjectApi } from "../../project/api";
import { type DocumentsRead, documentHref, latestOf } from "../../project/drafted";
import { Link } from "../../route";
import { InventoryChip } from "../conversation/InventoryChip";
import { STATES, documentName } from "../project/DocumentReview";
import { IssueLinks } from "../NotBuilt";

const NOT_BUILT: { label: string; issues: number[] }[] = [
  { label: "Dataset", issues: [160] },
  { label: "Phase", issues: [160] },
  { label: "Repository", issues: [160] },
  // TODO(#72, #39): governance flags have no single issue; the review gate and the
  // personal-data pause are the nearest.
  { label: "Governance", issues: [72, 39] },
];

/**
 * The project's documents, each with its latest version and that version's state, linked to its
 * place on the documents page, with how many wait for a decision in the heading.
 */
function ProjectDocuments({ projectId, read }: { projectId: string; read: DocumentsRead }) {
  const all = <Link to={`/projects/${encodeURIComponent(projectId)}`}>All documents in this project</Link>;
  const rows =
    read.state === "loaded"
      ? read.documents.flatMap((document) => {
          const latest = latestOf(document);
          return latest ? [{ document, latest }] : [];
        })
      : [];
  const waiting = rows.filter(({ latest }) => latest.state === "proposed").length;
  return (
    <section aria-labelledby="documents-heading">
      <h3 id="documents-heading">
        Documents
        {waiting > 0 && (
          <>
            {" "}
            <span className="documents-waiting">· {waiting} to review</span>
          </>
        )}
      </h3>
      {read.state === "loading" && <p>Reading the project&apos;s documents…</p>}
      {read.state === "failed" && (
        <p>
          Data Director could not read the project&apos;s documents: {read.message}. {all}.
        </p>
      )}
      {read.state === "loaded" &&
        (rows.length === 0 ? (
          <p>No documents drafted yet. When an agent drafts one, it is listed here for you to check.</p>
        ) : (
          <>
            <ul className="plain-list project-documents" aria-labelledby="documents-heading">
              {rows.map(({ document, latest }) => {
                const { label, className } = STATES[latest.state];
                return (
                  <li key={document.document_id}>
                    <Link to={documentHref(projectId, document.document_id)}>{documentName(document)}</Link>{" "}
                    <span className="hint">version {latest.version}</span>{" "}
                    <span className={`status ${className}`}>{label}</span>
                  </li>
                );
              })}
            </ul>
            <p>{all}, to approve, edit or reject.</p>
          </>
        ))}
    </section>
  );
}

export function ContextPanel({
  conversation = null,
  documents = { state: "loading" },
}: {
  conversation?: Conversation | null;
  /** The project's documents, as the workspace last read them. */
  documents?: DocumentsRead;
}) {
  const projectId = conversation?.project_id;
  const inventory = conversation?.inventory;
  const projectApi = useProjectApi();
  const source = useMemo<InventorySource | undefined>(
    () => (projectId ? { load: (signal) => projectApi.inventory(projectId, signal) } : undefined),
    [projectApi, projectId],
  );
  return (
    <section aria-labelledby="context-heading" className="workspace-context">
      <h2 id="context-heading">Project</h2>
      {!projectId && (
        <p>
          Your first message starts a project, which keeps the inventory you attach and the
          documents agents draft for you.
        </p>
      )}
      <section aria-labelledby="state-heading">
        <h3 id="state-heading">Current state</h3>
        <dl className="project-state">
          {NOT_BUILT.map(({ label, issues }) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <span className="status status-undeclared">Not built yet</span> (
                <IssueLinks issues={issues} />)
              </dd>
            </div>
          ))}
        </dl>
      </section>
      {projectId && (
        <>
          <section aria-labelledby="files-heading">
            <h3 id="files-heading">Attached files</h3>
            {inventory ? (
              <p>
                <InventoryChip
                  fileCount={inventory.file_count}
                  madeAt={inventory.inventory_made_at}
                  source={source}
                />
              </p>
            ) : (
              <p>
                No inventory of the dataset&apos;s files yet. Attach one to a message so that
                agents can describe the files. <a href={INVENTORY_GUIDE}>How do I make an inventory?</a>
              </p>
            )}
          </section>
          <ProjectDocuments projectId={projectId} read={documents} />
        </>
      )}
    </section>
  );
}
