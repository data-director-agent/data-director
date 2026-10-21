/**
 * The Run tab: the input form, the run's stages, and its outcome.
 *
 * A run is one request that answers when it has ended (`POST /api/runs`). While it runs the
 * stages are shown waiting; afterwards they are read back from the envelope. "Stop waiting"
 * only stops the page waiting: the run goes on in the conductor and appears in History.
 * Cancelling a run, and watching its stages live, need the AG-UI stream (#68, #69).
 *
 * The start and the end of a run are each announced once in a polite live region, and focus
 * moves to the outcome's heading when it arrives (checklist item 10).
 */

import { useEffect, useId, useRef, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { OUTCOME, className } from "../../manifest/wording";
import { RunRefused, errorMessage, useRunApi } from "../../run/api";
import { inferStages, pendingStages } from "../../run/stages";
import type { Example, RunResult } from "../../run/types";
import { Outcome } from "./Outcome";
import { RunForm } from "./RunForm";
import { Stages } from "./Stages";

type Phase =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "stopped" }
  | { kind: "error"; message: string }
  | { kind: "done"; result: RunResult };

export function RunView({ agent, onFinished }: { agent: AgentView; onFinished?: () => void }) {
  const api = useRunApi();
  const idPrefix = `run${useId().replace(/:/g, "")}`;
  const inputClasses = agent.accepts.filter((c) => agent.schemas[c]);
  const [schemaClass, setSchemaClass] = useState(inputClasses[0]);
  const [examples, setExamples] = useState<Example[]>([]);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [announcement, setAnnouncement] = useState("");
  const controller = useRef<AbortController | null>(null);
  const formHeading = useRef<HTMLHeadingElement>(null);
  const outcomeHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const abort = new AbortController();
    // Examples are a convenience: without them the form still works.
    api.examples(abort.signal).then(setExamples, () => undefined);
    return () => abort.abort();
  }, [api]);

  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    if (phase.kind === "done") outcomeHeading.current?.focus();
  }, [phase]);

  async function run(input: Record<string, unknown>) {
    if (phase.kind === "running") return;
    const abort = new AbortController();
    controller.current = abort;
    setPhase({ kind: "running" });
    setAnnouncement(`Running ${agent.id}.`);
    try {
      const result = await api.start(agent.id, input, abort.signal);
      setPhase({ kind: "done", result });
      setAnnouncement(`Run finished: ${OUTCOME[result.envelope.outcome.status].label}.`);
      onFinished?.();
    } catch (error) {
      if (abort.signal.aborted) return;
      const message =
        error instanceof RunRefused
          ? `${error.problem.title}: ${error.message}`
          : `Data Director could not run this: ${errorMessage(error)}`;
      setPhase({ kind: "error", message });
      setAnnouncement("");
    }
  }

  function stop() {
    controller.current?.abort();
    setPhase({ kind: "stopped" });
    setAnnouncement("Stopped waiting for the run.");
  }

  if (!schemaClass) {
    return <p>This agent takes no input class this deployment can describe, so it cannot be run here.</p>;
  }

  return (
    <div className="run-view">
      {agent.gate.kind !== "permitted" && (
        <div className="callout status-warn">
          <p>
            This deployment's policy will not let this agent run as asked. You can still run it,
            to see how Data Director refuses or refers it. See About for why.
          </p>
        </div>
      )}

      {inputClasses.length > 1 && (
        <div className="field">
          <label htmlFor={`${idPrefix}-class`}>Input class</label>
          <select
            id={`${idPrefix}-class`}
            value={schemaClass}
            onChange={(e) => setSchemaClass(e.target.value)}
          >
            {inputClasses.map((c) => (
              <option key={c} value={c}>
                {className(c)}
              </option>
            ))}
          </select>
        </div>
      )}

      <RunForm
        key={schemaClass}
        schemaClass={schemaClass}
        schema={agent.schemas[schemaClass] ?? {}}
        examples={examples}
        running={phase.kind === "running"}
        onRun={(input) => void run(input)}
        headingRef={formHeading}
      />

      <p role="status" className="visually-hidden">
        {announcement}
      </p>

      {phase.kind === "running" && (
        <>
          <Stages stages={pendingStages()} inferred={false} />
          <p>
            <button type="button" onClick={stop}>
              Stop waiting
            </button>
          </p>
        </>
      )}
      {phase.kind === "stopped" && (
        <div className="callout">
          <p>
            Stopped waiting. The run may still finish in Data Director; if it does, it is in
            History. Cancelling a run is not built yet (#68).
          </p>
        </div>
      )}
      {phase.kind === "error" && (
        <div className="callout status-danger" role="alert">
          <p>{phase.message}</p>
        </div>
      )}
      {phase.kind === "done" && (
        <>
          <Stages stages={inferStages(phase.result)} inferred />
          <Outcome
            result={phase.result}
            agent={agent}
            idPrefix={idPrefix}
            headingRef={outcomeHeading}
            onEditInput={() => formHeading.current?.focus()}
          />
        </>
      )}
    </div>
  );
}
