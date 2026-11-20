/**
 * A document version drafted on a turn, shown on that turn so that the researcher sees what the
 * turn produced without opening its run (docs/specs/app.md). The card names the document, its
 * version and the state the project log records, and says when a later version has replaced it.
 * Its preview, closed at first, shows the text as a run's result does, with copy and download.
 * Deciding on the version is done on the project's documents page, which the card links to, so
 * that there is one place where a decision is made, with its rules. While the version is its
 * document's latest, the card puts its open questions to the researcher, a few at a time
 * (`DocumentQuestions`, docs/specs/drafting.md).
 *
 * A version at the `questions` stage is not the document yet: the drafter asks what it needs
 * before it writes it. Its card shows the questions open, with no preview and nothing to approve,
 * and offers to write the document once they are answered.
 */

import "./DocumentCard.css";

import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import { useState } from "react";

import type { ProjectDocuments } from "../../project/api";
import { type DraftedVersion, documentHref } from "../../project/drafted";
import { Link } from "../../route";
import { DocumentText } from "../run/result/DocumentText";
import { documentName } from "../../project/name";
import { STATES } from "../project/DocumentFacts";
import { Button } from "../ui/Button";
import { DocumentQuestions } from "./DocumentQuestions";

export function DocumentCard({
  projectId,
  drafted,
  idPrefix,
  onAnswered,
  onWrite,
}: {
  projectId: string;
  drafted: DraftedVersion;
  /** Unique within the page, for the preview's ids. */
  idPrefix: string;
  /** Called with the project's documents after the researcher answers; without it, the card
   * asks nothing. */
  onAnswered?: (value: ProjectDocuments) => void;
  /** Asks in the conversation for the document to be written, for a `questions` version. */
  onWrite?: (message: string) => void;
}) {
  const { document, version, latest } = drafted;
  const [open, setOpen] = useState(false);
  const name = documentName(document);
  const which = `${name}, version ${version.version}`;
  const regionId = `${idPrefix}-preview`;
  const { label, className } = STATES[version.state];
  const by = version.drafted_by;
  const asking = version.stage === "questions";
  return (
    <li className="callout document-card">
      <p className="document-card-title">
        <FileText
          className="document-card-icon"
          size="1.25em"
          aria-hidden="true"
        />
        <span>
          <strong>{name}</strong>, version {version.version}{" "}
          {asking ? (
            <span className="status">Questions first</span>
          ) : (
            <span className={`status ${className}`}>{label}</span>
          )}
        </span>
      </p>
      <p className="hint">
        {by && (
          <>
            Drafted by{" "}
            <code>
              {by.agent_id}@{by.agent_version}
            </code>
            .
          </>
        )}
        {latest.version !== version.version && (
          <> Version {latest.version} is now the latest.</>
        )}
      </p>
      {asking && (
        <p>
          Before writing the {name}, the drafter asks what only you can say.
          Answer what you can, then ask for the {name} to be written: it is
          written from your answers, and anything left unanswered is marked as
          still needed.
        </p>
      )}
      <p hidden={asking}>
        <Button
          size="small"
          icon={open ? ChevronUp : ChevronDown}
          aria-expanded={open}
          aria-controls={regionId}
          onPress={() => setOpen((was) => !was)}
        >
          {open ? "Hide the preview" : "Preview"}{" "}
          <span className="visually-hidden">of {which}</span>
        </Button>{" "}
        <Link to={documentHref(projectId, document.document_id)}>
          {latest.state === "proposed"
            ? "Review and approve"
            : "Open in the project's documents"}{" "}
          <span className="visually-hidden">{name}</span>
        </Link>
      </p>
      <div id={regionId} className="document-card-preview" hidden={!open}>
        {open && (
          <DocumentText
            text={version.text}
            mediaType={version.media_type}
            title={name}
            headingId={`${idPrefix}-heading`}
          />
        )}
      </div>
      {onAnswered && latest.version === version.version && (
        <DocumentQuestions
          projectId={projectId}
          document={document}
          version={version}
          name={name}
          onAnswered={onAnswered}
          {...(asking && onWrite ? { onWrite } : {})}
        />
      )}
    </li>
  );
}
