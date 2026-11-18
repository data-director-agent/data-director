/**
 * A delegated child's work, opened in its card in the transcript (docs/specs/app.md): its outcome,
 * result and evidence, drawn by the run view's own `Outcome` rather than a second rendering, so
 * the evidence sits beside the turn it supports. It is read from the run store once the run has
 * ended; a child has no stages of its own (its parent's stream reports it as `SUBAGENT_*`
 * events, in the activity log), so none are drawn.
 */

import { type Ref, useEffect, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import type { ProjectSummary } from "../../project/api";
import { errorMessage, useRunApi } from "../../run/api";
import type { RunResult } from "../../run/types";
import { Outcome } from "../run/Outcome";

type Loaded = { id: string; result: RunResult | null; error?: string };

export function RunDetail({
  invocationId,
  agents,
  idPrefix,
  headingRef,
  project,
}: {
  invocationId: string;
  /** The directory, in which the run's own agent is found once the run is loaded. */
  agents: AgentView[];
  idPrefix: string;
  headingRef?: Ref<HTMLHeadingElement>;
  /** The project of the conversation that started the run; null if it has none, and left out
   * if that is not known. */
  project?: ProjectSummary | null | undefined;
}) {
  const runs = useRunApi();
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let current = true;
    runs.get(invocationId).then(
      (result) => current && setLoaded({ id: invocationId, result }),
      (e: unknown) => current && setLoaded({ id: invocationId, result: null, error: errorMessage(e) }),
    );
    return () => {
      current = false;
    };
  }, [runs, invocationId]);

  const shown = loaded?.id === invocationId ? loaded : null;
  const agent = shown?.result && agents.find((a) => a.id === shown.result?.envelope.agent_id);
  return (
    <>
      {shown?.error && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not open this run: {shown.error}.</p>
        </div>
      )}
      {!shown && <p role="status">Opening the run…</p>}
      {shown?.result && agent && (
        <>
          <Outcome
            result={shown.result}
            agent={agent}
            idPrefix={idPrefix}
            project={project}
            {...(headingRef ? { headingRef } : {})}
          />
        </>
      )}
      {shown?.result && !agent && (
        <p>
          {shown.result.envelope.outcome.statement} This agent is not in the directory, so its full
          run view is not available.
        </p>
      )}
    </>
  );
}
