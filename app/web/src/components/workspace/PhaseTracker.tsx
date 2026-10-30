/**
 * The Blueprint's six phases (§8.2), each with its steps, the requirements applied at each, and
 * which of the agents here serve them (ADR-0028). The phases come from the server's process flow
 * and the agents from the manifest; the tracker names no agent of its own.
 *
 * Where the researcher stands in these phases is not known yet: that needs a record of the
 * project (#160), so it is drawn as not built rather than guessed.
 */

import "./PhaseTracker.css";

import type { AgentView } from "../../manifest/normalise";
import { Link } from "../../route";
import { servingIndex, servingStep } from "../../flow/serving";
import type { ProcessFlow } from "../../flow/types";
import { NotBuilt } from "../NotBuilt";

export type FlowLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; flow: ProcessFlow };

export function PhaseTracker({ load, agents }: { load: FlowLoad; agents: AgentView[] }) {
  return (
    <nav aria-labelledby="phases-heading" className="workspace-phases">
      <h2 id="phases-heading">Blueprint phases</h2>
      <NotBuilt title="Where your project is in these phases" issues={[160]} />
      {load.state === "loading" && <p role="status">Loading the phases…</p>}
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not load the Blueprint's phases: {load.message}.</p>
        </div>
      )}
      {load.state === "loaded" && <Phases flow={load.flow} agents={agents} />}
    </nav>
  );
}

function Phases({ flow, agents }: { flow: ProcessFlow; agents: AgentView[] }) {
  const index = servingIndex(agents);
  const titles = new Map(agents.map((a) => [a.id, a.title]));
  return (
    <ol className="phase-list">
      {flow.phases.map((phase) => {
        const served = phase.steps.filter((s) => servingStep(s, index).length > 0).length;
        return (
          <li key={phase.number}>
            <details>
              <summary>
                <span className="phase-number">Phase {phase.number}</span> {phase.title}{" "}
                <span className="muted phase-served">
                  ({served} of {phase.steps.length} {phase.steps.length === 1 ? "step" : "steps"}{" "}
                  with an agent here)
                </span>
              </summary>
              <ol className="step-list">
                {phase.steps.map((step) => {
                  const serving = servingStep(step, index);
                  return (
                    <li key={step.text}>
                      <p className="step-text">
                        {step.text}
                        {step.optional && <span className="muted"> (optional)</span>}
                      </p>
                      <p className="step-meta">
                        {step.requirements.length > 0
                          ? `Requirements: ${step.requirements.join(", ")}. `
                          : "The Blueprint names no requirement here. "}
                        {serving.length > 0 ? (
                          <>
                            Served by{" "}
                            {serving.map((id, i) => (
                              <span key={id}>
                                {i > 0 && ", "}
                                <Link to={`/agents?agent=${encodeURIComponent(id)}`}>
                                  {titles.get(id) || <code>{id}</code>}
                                </Link>
                              </span>
                            ))}
                            .
                          </>
                        ) : (
                          "No agent here serves this step."
                        )}
                      </p>
                    </li>
                  );
                })}
              </ol>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
