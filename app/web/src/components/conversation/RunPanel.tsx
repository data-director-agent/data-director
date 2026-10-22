/**
 * The selected delegated child's work, beside the conversation (#135): its progress, outcome,
 * result and evidence, drawn by the run view's own `Stages` and `Outcome` rather than a second
 * rendering. Beside the transcript on a wide screen; its own view, reached from the card, on a
 * narrow one (the layout rules are in `base.css`).
 */

import { forwardRef, useEffect, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { errorMessage, useRunApi } from "../../run/api";
import { inferStages } from "../../run/stages";
import type { RunResult } from "../../run/types";
import { Outcome } from "../run/Outcome";
import { Stages } from "../run/Stages";

type Loaded = { id: string; result: RunResult | null; error?: string };

export const RunPanel = forwardRef<
  HTMLHeadingElement,
  { invocationId: string; agent: AgentView | undefined; name: string; onClose: () => void }
>(function RunPanel({ invocationId, agent, name, onClose }, heading) {
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
  return (
    <section aria-labelledby="open-run" className="run-panel">
      <p>
        <button type="button" onClick={onClose}>
          Back to the conversation
        </button>
      </p>
      <h2 id="open-run" ref={heading} tabIndex={-1}>
        Run of {name}
      </h2>
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
          <Outcome result={shown.result} agent={agent} idPrefix="conversation-run" />
        </>
      )}
      {shown?.result && !agent && (
        <p>
          {shown.result.envelope.outcome.statement} This agent is not in the directory, so its full
          run view is not available.
        </p>
      )}
    </section>
  );
});
