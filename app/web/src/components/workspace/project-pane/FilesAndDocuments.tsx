/**
 * What the project holds for the conversation to work on and what it has produced: the inventory
 * of the dataset's files, then its documents, those this conversation drafted first, each with
 * its latest version's state. A version is this conversation's when one of its runs drafted it,
 * matched by invocation as the transcript matches it (`draftedBy`). The list is short; the
 * documents page holds them all and is where they are decided.
 */

import { useMemo, useState } from "react";

import { INVENTORY_GUIDE, type InventorySource } from "../../../conversation/inventory";
import type { Conversation } from "../../../conversation/types";
import { type ProjectDocument, type SavedInventory, useProjectApi } from "../../../project/api";
import { type DocumentsRead, documentHref, draftedBy, latestOf } from "../../../project/drafted";
import { documentName } from "../../../project/name";
import { Link, projectTabPath } from "../../../route";
import { InventoryChip } from "../../conversation/InventoryChip";
import { AddInventory } from "../../inventory/AddInventory";
import { InventoryEditDialog } from "../../inventory/InventoryEditDialog";
import { STATES } from "../../project/DocumentFacts";

const SHOWN = 5;

function Inventory({
  projectId,
  held,
  onInventorySaved,
}: {
  projectId: string;
  held: SavedInventory | null | undefined;
  onInventorySaved?: (() => void) | undefined;
}) {
  // An inventory saved here is newer than any read of the project.
  const [saved, setSaved] = useState<{ projectId: string; inventory: SavedInventory } | null>(null);
  const inventory = saved && saved.projectId === projectId ? saved.inventory : held;
  const projectApi = useProjectApi();
  const source = useMemo<InventorySource>(
    () => ({ load: (signal) => projectApi.inventory(projectId, signal) }),
    [projectApi, projectId],
  );
  const onSaved = (next: SavedInventory) => {
    setSaved({ projectId, inventory: next });
    onInventorySaved?.();
  };
  return (
    <div className="pane-inventory">
      {inventory ? (
        <p>
          <InventoryChip fileCount={inventory.file_count} madeAt={inventory.inventory_made_at} source={source} />{" "}
          <InventoryEditDialog projectId={projectId} onSaved={onSaved} />
        </p>
      ) : (
        <p className="hint">
          No inventory of the dataset&apos;s files yet. Add one so that agents can describe the files.{" "}
          <a href={INVENTORY_GUIDE}>How do I make an inventory?</a>
        </p>
      )}
      <p>
        <AddInventory projectId={projectId} replacing={Boolean(inventory)} onSaved={onSaved} />
      </p>
    </div>
  );
}

function DocumentList({
  label,
  projectId,
  documents,
}: {
  label: string;
  projectId: string;
  documents: readonly ProjectDocument[];
}) {
  if (documents.length === 0) return null;
  return (
    <>
      <h4>{label}</h4>
      <ul className="plain-list pane-rows" aria-label={label}>
        {documents.map((document) => {
          const latest = latestOf(document);
          if (!latest) return null;
          const { label: state, className } = STATES[latest.state];
          return (
            <li key={document.document_id}>
              <span>
                <Link to={documentHref(projectId, document.document_id)}>{documentName(document)}</Link>{" "}
                <span className="hint">version {latest.version}</span>
              </span>
              <span className={`status ${className}`}>{state}</span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** The conversation's invocations: each turn's and those of the runs it delegated to. */
function invocationsOf(conversation: Conversation | null): string[] {
  return (conversation?.turns ?? []).flatMap((turn) => [
    turn.invocation_id,
    ...turn.children.map((child) => child.invocation_id),
  ]);
}

function Documents({
  projectId,
  read,
  conversation,
}: {
  projectId: string;
  read: DocumentsRead;
  conversation: Conversation | null;
}) {
  const all = <Link to={projectTabPath(projectId)}>All documents</Link>;
  if (read.state === "loading") return <p className="hint">Reading the project&apos;s documents…</p>;
  if (read.state === "failed") {
    return (
      <p className="hint">
        Data Director could not read the project&apos;s documents: {read.message}. {all}.
      </p>
    );
  }
  const listed = read.documents.filter((d) => latestOf(d));
  if (listed.length === 0) {
    return <p className="hint">No documents drafted yet. When an agent drafts one, it is listed here.</p>;
  }
  const ours = new Set(draftedBy(invocationsOf(conversation), read.documents).map((d) => d.document.document_id));
  const here = listed.filter((d) => ours.has(d.document_id)).slice(0, SHOWN);
  const earlier = listed.filter((d) => !ours.has(d.document_id)).slice(0, Math.max(0, SHOWN - here.length));
  return (
    <>
      <DocumentList label="From this conversation" projectId={projectId} documents={here} />
      <DocumentList label={here.length > 0 ? "Earlier" : "In this project"} projectId={projectId} documents={earlier} />
      <p className="pane-actions">
        {all}
        {listed.length > here.length + earlier.length && (
          <span className="hint"> ({listed.length})</span>
        )}
      </p>
    </>
  );
}

export function FilesAndDocuments({
  projectId,
  inventory,
  documents,
  conversation,
  onInventorySaved,
}: {
  projectId: string;
  inventory: SavedInventory | null | undefined;
  documents: DocumentsRead;
  conversation: Conversation | null;
  onInventorySaved?: (() => void) | undefined;
}) {
  return (
    <section aria-labelledby="files-heading" className="pane-section">
      <h3 id="files-heading">Files and documents</h3>
      <Inventory projectId={projectId} held={inventory} onInventorySaved={onInventorySaved} />
      <Documents projectId={projectId} read={documents} conversation={conversation} />
    </section>
  );
}
