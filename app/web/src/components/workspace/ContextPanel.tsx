/**
 * Beside the conversation, an overview of the project it was started in (docs/specs/app.md):
 * where the project stands, the files attached to it (the inventory it holds) and a link to the
 * documents agents have drafted in it. Where it stands, its dataset, phase, repository and open
 * governance flags, needs a record of the project (#160), so each is drawn as not built, linked
 * to its issues, with no value standing in for it. A delegated run and its evidence open in the
 * transcript, beside the turn they support.
 */

import "./ContextPanel.css";

import { INVENTORY_GUIDE } from "../../conversation/inventory";
import type { Conversation } from "../../conversation/types";
import { Link } from "../../route";
import { InventoryChip } from "../conversation/InventoryChip";
import { IssueLinks } from "../NotBuilt";

const NOT_BUILT: { label: string; issues: number[] }[] = [
  { label: "Dataset", issues: [160] },
  { label: "Phase", issues: [160] },
  { label: "Repository", issues: [160] },
  // TODO(#72, #39): governance flags have no single issue; the review gate and the
  // personal-data pause are the nearest.
  { label: "Governance", issues: [72, 39] },
];

export function ContextPanel({ conversation = null }: { conversation?: Conversation | null }) {
  const projectId = conversation?.project_id;
  const inventory = conversation?.inventory;
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
                />
              </p>
            ) : (
              <p>
                No inventory of the dataset&apos;s files yet. Attach one to a message so that
                agents can describe the files. <a href={INVENTORY_GUIDE}>How do I make an inventory?</a>
              </p>
            )}
          </section>
          <section aria-labelledby="documents-heading">
            <h3 id="documents-heading">Documents</h3>
            <p>
              <Link to={`/projects/${encodeURIComponent(projectId)}`}>
                The documents drafted in this project
              </Link>
              , to approve, edit or reject.
            </p>
          </section>
        </>
      )}
    </section>
  );
}
