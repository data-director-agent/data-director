/**
 * Where the project's metadata record stands against the FAIR checks, from the reports stored in
 * the project (docs/ui/fair-feedback.md): the latest report, what changed since the one before,
 * which run gave it, and whether the record has changed since, which is the prompt to check again.
 * The project pane shows it compact; the project's FAIR feedback tab in full.
 */

import { RefreshCw } from "lucide-react";

import type { ProjectDocument } from "../../project/api";
import {
  ASK_FOR_FEEDBACK,
  type Assessment,
  hasMetadataRecord,
  newerVersion,
  totalOf,
} from "../../project/fairness";
import type { Resource } from "../../useResource";
import { Button } from "../ui/Button";
import { FairnessReportView } from "./FairnessReportView";

type Ask = ((text: string) => void) | undefined;

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

/** Which run gave the report, and on which version of the record: a report always names its source. */
export function Source({ assessment }: { assessment: Assessment }) {
  const { envelope, report } = assessment;
  const version = report.assessed_version
    ? `, on version ${report.assessed_version.version}`
    : "";
  return (
    <p className="hint fair-source">
      Rule checks by {envelope.agent_id}@{envelope.agent_version},{" "}
      {when(envelope.completed_at)}
      {version}. Not a FAIRness evaluation.
    </p>
  );
}

function AskAgain({ onAsk, label }: { onAsk: Ask; label: string }) {
  if (!onAsk) return null;
  return (
    <Button
      size="small"
      icon={RefreshCw}
      onPress={() => onAsk(ASK_FOR_FEEDBACK)}
    >
      {label}
    </Button>
  );
}

/** Nothing stored yet: what to do to get the first report. */
function NoReport({
  documents,
  onAsk,
}: {
  documents: readonly ProjectDocument[];
  onAsk: Ask;
}) {
  if (!hasMetadataRecord(documents)) {
    return (
      <p className="hint">
        Once the project has a draft metadata record, Data Director can say
        which FAIR checks it meets and what to improve next.
      </p>
    );
  }
  return (
    <>
      <p>
        See which FAIR checks the draft metadata record meets, and what to
        improve next.
      </p>
      <AskAgain onAsk={onAsk} label="How FAIR is it?" />
    </>
  );
}

export function FairnessStanding({
  history,
  documents,
  onAsk,
  compact = false,
}: {
  history: Resource<Assessment[]>;
  documents: readonly ProjectDocument[];
  /** Puts a question in the message box, unsent; with none, no question is offered. */
  onAsk?: Ask;
  compact?: boolean;
}) {
  if (history.state === "loading")
    return <p className="hint">Reading the FAIR feedback…</p>;
  if (history.state === "failed") {
    return (
      <p className="hint">
        Data Director could not read the FAIR feedback: {history.message}.
      </p>
    );
  }
  const [latest, previous] = history.value;
  if (!latest) return <NoReport documents={documents} onAsk={onAsk} />;
  const newer = newerVersion(latest.report, documents);
  const total = totalOf(latest.report);
  return (
    <>
      <p className="fair-headline">
        {total.met} of {total.assessed} checks a draft can meet are met.
      </p>
      {newer !== null && (
        <p className="fair-stale" role="note">
          The metadata record has changed since this check (now version {newer}
          ).
        </p>
      )}
      <FairnessReportView
        report={latest.report}
        previous={previous?.report ?? null}
        onAsk={onAsk}
        compact={compact}
        headingLevel={compact ? 4 : 3}
      />
      <Source assessment={latest} />
      <AskAgain
        onAsk={onAsk}
        label={newer !== null ? "Check the new version" : "Check again"}
      />
    </>
  );
}
