/**
 * A delegated child's work, opened in its card in the transcript (ADR-0024 §14): its progress,
 * outcome, result and evidence, drawn by the run view's own `Stages` and `Outcome` rather than
 * a second rendering, so the evidence sits beside the turn it supports.
 */

import { type Ref, useEffect, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { errorMessage, useRunApi } from "../../run/api";
import { inferStages } from "../../run/stages";
import type { RunResult } from "../../run/types";
import { Outcome } from "../run/Outcome";
import { Stages } from "../run/Stages";

type Loaded = { id: string; result: RunResult | null; error?: string };

export function RunDetail({
  invocationId,
  agents,
  idPrefix,
  headingRef,
}: {
  invocationId: string;
  /** The directory, in which the run's own agent is found once the run is loaded. */
  agents: AgentView[];
  idPrefix: string;
  headingRef?: Ref<HTMLHeadingElement>;
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
          <h3 className="visually-hidden">Progress and outcome</h3>
          <Stages stages={inferStages(shown.result)} inferred />
          <Outcome
            result={shown.result}
            agent={agent}
            idPrefix={idPrefix}
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
