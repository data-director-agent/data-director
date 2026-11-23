/**
 * A run the person asks of a document's drafter from the documents page, to continue drafting it
 * (`ContinueDrafting`) or to revise it as they ask (`RevisionRequest`), and what it said. The
 * outcome is kept in a status: the new version's number, or why the agent drew none, in its own
 * statement. A request the server refused because the document has moved on is passed to
 * `onStale`, as a decision is; any other failure is said in an alert.
 */

import { useState } from "react";

import { DecisionConflict, type ProjectDocuments } from "../../project/api";

/** The run's outcome as the server reports it after the request. */
type Run = ProjectDocuments["drafted"];

interface Said {
  text: string;
  drafted: boolean;
}

export interface DraftRun {
  sending: boolean;
  said: Said | null;
  error: string | null;
  /** Sends `request`; reads its run with `outcome` and says a drafted version with `drafted`.
   * Answers whether the agent drafted a version. */
  start(
    request: () => Promise<ProjectDocuments>,
    outcome: (value: ProjectDocuments) => Run,
    drafted: (version: number) => string,
  ): Promise<boolean>;
}

export function useDraftRun(
  onDone: (value: ProjectDocuments) => void,
  onStale: (detail: string) => Promise<void>,
): DraftRun {
  const [sending, setSending] = useState(false);
  const [said, setSaid] = useState<Said | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(
    request: () => Promise<ProjectDocuments>,
    outcome: (value: ProjectDocuments) => Run,
    drafted: (version: number) => string,
  ): Promise<boolean> {
    setSending(true);
    setError(null);
    setSaid(null);
    try {
      const value = await request();
      const run = outcome(value);
      const version = run?.version ?? null;
      setSaid(
        version
          ? { text: drafted(version.version), drafted: true }
          : { text: `No new version: ${run?.statement ?? "the agent drafted none."}`, drafted: false },
      );
      onDone(value);
      return version !== null;
    } catch (caught) {
      if (caught instanceof DecisionConflict) await onStale(caught.message);
      else setError(caught instanceof Error ? caught.message : String(caught));
      return false;
    } finally {
      setSending(false);
    }
  }

  return { sending, said, error, start };
}

/** The alert for a request not sent, and the status saying the run's outcome or that it runs. */
export function DraftRunStatus({ run, sending }: { run: DraftRun; sending: string }) {
  return (
    <>
      {run.error && (
        <div role="alert" className="callout status-danger">
          <p>The request was not sent: {run.error}</p>
        </div>
      )}
      <p role="status" className={run.said && !run.said.drafted ? "callout status-warn" : undefined}>
        {run.sending ? sending : (run.said?.text ?? "")}
      </p>
    </>
  );
}
