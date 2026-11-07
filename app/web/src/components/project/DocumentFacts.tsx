/**
 * The facts said about each version of a document: its state and who decided it, and who drafted
 * or edited it and when. The reader, its history and the document list share them.
 */

import type { DocumentVersion, VersionState } from "../../project/api";

export const STATES: Record<VersionState, { label: string; className: string }> = {
  proposed: { label: "Proposed, not reviewed", className: "status-warn" },
  approved: { label: "Approved", className: "status-ok" },
  rejected: { label: "Rejected", className: "status-danger" },
};

export function When({ at }: { at: string }) {
  const shown = new Date(at).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
  return <time dateTime={at}>{shown}</time>;
}

export function Provenance({ version }: { version: DocumentVersion }) {
  const by = version.drafted_by;
  return (
    <>
      {by ? (
        <>
          Drafted by{" "}
          <code>
            {by.agent_id}@{by.agent_version}
          </code>
        </>
      ) : (
        <>Edited by {version.added_by.name}</>
      )}
      {" on "}
      <When at={version.added_at} />
    </>
  );
}

export function State({ version }: { version: DocumentVersion }) {
  const { label, className } = STATES[version.state];
  const decision = version.decision;
  return (
    <>
      <span className={`status ${className}`}>{label}</span>
      {decision && (
        <>
          {" "}
          by {decision.decided_by.name} on <When at={decision.decided_at} />
        </>
      )}
    </>
  );
}
