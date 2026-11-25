/**
 * Ask the agent that drafted a document to draft it again from the project's recorded answers
 * (docs/specs/drafting.md, invariant 10), so that the person can keep the document moving towards
 * complete without going back to the conversation. It is offered beneath the latest version of a
 * document an agent drafted, at either stage and whether or not any question is still open: a
 * version that only asks questions becomes the document, and a draft is written again with every
 * answer recorded since put in place.
 *
 * The outcome is said as `DraftRun` says it.
 */

import { PenLine } from "lucide-react";
import { versionGaps } from "../../project/gaps";
import {
  type DocumentVersion,
  type ProjectDocument,
  type ProjectDocuments,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";
import { DraftRunStatus, useDraftRun } from "./DraftRun";

/** What a new draft will do with the answers recorded and the questions still open. */
function hint(document: ProjectDocument, version: DocumentVersion, name: string): string {
  const { gaps, open } = versionGaps(document, version);
  const writes =
    version.stage === "questions"
      ? `The agent that drafted the ${name} writes it from the answers recorded so far.`
      : `The agent that drafted the ${name} writes a new version with every answer recorded so far put in place.`;
  if (open > 0) return `${writes} Questions you have not answered stay open in the new version.`;
  if (gaps > 0) return `${writes} Every question on this version has an answer.`;
  return `${writes} It may find more to ask.`;
}

export function ContinueDrafting({
  projectId,
  document,
  version,
  name,
  isLatest,
  onDrafted,
  onStale,
}: {
  projectId: string;
  document: ProjectDocument;
  /** The version shown, which the request names if it is the latest. */
  version: DocumentVersion;
  name: string;
  isLatest: boolean;
  /** Called with the project's documents as the server read them back after the run. */
  onDrafted: (value: ProjectDocuments) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const api = useProjectApi();
  const run = useDraftRun(onDrafted, onStale);
  if (!isLatest || !document.versions.some((v) => v.drafted_by)) return null;

  function draft() {
    void run.start(
      () => api.draft(projectId, version.document_id, version.version),
      (value) => value.drafted,
      (n) =>
        `Version ${n} is the next draft of the ${name}. Read it, and compare it with version ${version.version} in Versions, before you decide on it.`,
    );
  }

  return (
    <section className="revision-request continue-drafting" aria-label="Continue drafting">
      <p className="hint">{hint(document, version, name)}</p>
      <DraftRunStatus run={run} sending={`Drafting the ${name} again…`} />
      <Button icon={PenLine} isDisabled={run.sending} onPress={draft}>
        {run.sending ? "Drafting…" : "Continue drafting"}
      </Button>
    </section>
  );
}
