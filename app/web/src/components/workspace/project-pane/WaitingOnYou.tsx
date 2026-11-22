/**
 * The top of the project pane: everything in the project that waits on a person, one row each
 * with the one thing to do about it. Documents and facts are decided on the project's pages, not
 * here (docs/specs/app.md), so their rows go there; a repository warning is asked about in the
 * conversation. The review gate and the personal-data pause are not built (#72, #39).
 */

import type { ReactNode } from "react";

import type { ProjectDocument, ProjectSummary } from "../../../project/api";
import { documentHref, latestOf } from "../../../project/drafted";
import { type ProjectFacts, factKey } from "../../../project/facts";
import { documentName } from "../../../project/name";
import { factsPath, Link } from "../../../route";
import type { Resource } from "../../../useResource";
import { IssueLinks } from "../../NotBuilt";
import { KIND_LABELS, describeFact } from "../../project/factWording";
import { Button } from "../../ui/Button";
import { proposalsByKind } from "./facts";

interface Row {
  key: string;
  what: ReactNode;
  action: ReactNode;
}

const GATE_ISSUES = [72, 39];

function documentRows(projectId: string, documents: readonly ProjectDocument[]): Row[] {
  return documents.flatMap((document) => {
    const latest = latestOf(document);
    if (latest?.state !== "proposed") return [];
    return [
      {
        key: `document:${document.document_id}`,
        what: (
          <>
            <strong>{documentName(document)}</strong> <span className="hint">version {latest.version}</span>{" "}
            to review
          </>
        ),
        action: (
          <Link className="button button-secondary button-small" to={documentHref(projectId, document.document_id)}>
            Review
          </Link>
        ),
      },
    ];
  });
}

function factRows(projectId: string, facts: ProjectFacts): Row[] {
  return proposalsByKind(facts.proposals).map(([kind, proposals]) => {
    const [only] = proposals;
    return {
      key: `facts:${kind}`,
      what:
        proposals.length === 1 && only ? (
          <>
            <strong>{KIND_LABELS[kind]}</strong> proposed: {describeFact(only.fact)}
          </>
        ) : (
          <>
            <strong>{KIND_LABELS[kind]}</strong>: {proposals.length} proposals to decide
          </>
        ),
      // Lands on these proposals on the facts page, where they are decided.
      action: (
        <Link
          className="button button-secondary button-small"
          aria-label={`Review ${KIND_LABELS[kind]}`}
          to={factsPath(projectId, proposals.map((p) => factKey(p.fact)))}
        >
          Review
        </Link>
      ),
    };
  });
}

function warningRows(project: ProjectSummary | null, onAsk: ((text: string) => void) | undefined): Row[] {
  const repository = project?.repository;
  if (!repository) return [];
  return repository.warnings.map((warning) => ({
    key: `warning:${warning}`,
    what: (
      <>
        <span className="status status-warn">Warning</span> {repository.repository_name}: {warning}
      </>
    ),
    action: onAsk ? (
      <Button
        size="small"
        onPress={() =>
          onAsk(`The choice of ${repository.repository_name} warns that ${warning}. What does that mean for the deposit?`)
        }
      >
        Ask why
      </Button>
    ) : null,
  }));
}

function intakeRows(project: ProjectSummary | null): Row[] {
  if (project?.intake !== "pending") return [];
  return [
    {
      key: "intake",
      what: (
        <>
          <strong>Setup questions</strong> not answered yet
        </>
      ),
      action: <span className="hint">Answer them in the conversation</span>,
    },
  ];
}

export function WaitingOnYou({
  projectId,
  project,
  documents,
  facts,
  onAsk,
}: {
  projectId: string;
  project: ProjectSummary | null;
  documents: readonly ProjectDocument[];
  facts: Resource<ProjectFacts>;
  onAsk?: ((text: string) => void) | undefined;
}) {
  const rows = [
    ...documentRows(projectId, documents),
    ...(facts.state === "loaded" ? factRows(projectId, facts.value) : []),
    ...warningRows(project, onAsk),
    ...intakeRows(project),
  ];
  return (
    <section aria-labelledby="waiting-heading" className="pane-section pane-waiting">
      <h3 id="waiting-heading">
        Waiting on you
        {rows.length > 0 && <span className="pane-count"> · {rows.length}</span>}
      </h3>
      {rows.length === 0 ? (
        <p className="hint">Nothing waits on you.</p>
      ) : (
        <ul className="plain-list pane-rows" aria-labelledby="waiting-heading">
          {rows.map(({ key, what, action }) => (
            <li key={key}>
              <span>{what}</span>
              {action}
            </li>
          ))}
        </ul>
      )}
      {facts.state === "failed" && (
        <p className="hint">Data Director could not read the project&apos;s facts: {facts.message}.</p>
      )}
      <p className="hint">
        <span className="status status-undeclared">Not built yet</span> Approvals before an agent acts,
        and the pause for personal data (<IssueLinks issues={GATE_ISSUES} />)
      </p>
    </section>
  );
}
