/**
 * The journey from planning a dataset to sharing it, in a researcher's words: six phases, each
 * with the things they will do in it. It names no agent and no Blueprint requirement; which
 * agents help is for the conversation to say. The phases come from the server's process flow, so
 * the shell keeps no copy of it.
 *
 * Drawn as a strip, like a progress bar, opening to show each phase's steps. Where the
 * researcher stands in it is not known yet: that needs a record of the project (#160), so it is
 * drawn as not built rather than guessed.
 */

import "./PhaseTracker.css";

import type { ProcessFlow } from "../../flow/types";
import { IssueLinks } from "../NotBuilt";

export type FlowLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; flow: ProcessFlow };

export function PhaseTracker({ load }: { load: FlowLoad }) {
  return (
    <nav aria-labelledby="phases-heading" className="workspace-phases phase-strip">
      <div className="phase-strip-head">
        <h2 id="phases-heading">Your data journey</h2>
        <p className="phase-strip-where">
          Where your project is: <span className="status status-undeclared">Not built yet</span>{" "}
          (<IssueLinks issues={[160]} />)
        </p>
      </div>
      {load.state === "loading" && <p role="status">Loading the journey…</p>}
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not load the journey: {load.message}.</p>
        </div>
      )}
      {load.state === "loaded" && (
        <>
          <ol className="phase-bar" aria-label="The phases in order">
            {load.flow.phases.map((phase) => (
              <li key={phase.number} className="phase-bar-segment">
                <span className="phase-bar-number" aria-hidden="true">
                  {phase.number}
                </span>
                <span className="phase-bar-title">{phase.name}</span>
              </li>
            ))}
          </ol>
          <details className="phase-strip-details">
            <summary>Show what happens in each phase</summary>
            <Phases flow={load.flow} />
          </details>
        </>
      )}
    </nav>
  );
}

function Phases({ flow }: { flow: ProcessFlow }) {
  return (
    <ol className="phase-list">
      {flow.phases.map((phase) => (
        <li key={phase.number}>
          <details>
            <summary>
              <span className="phase-number">Phase {phase.number}</span> {phase.name}
            </summary>
            <p className="phase-summary">{phase.summary}</p>
            <ol className="step-list">
              {phase.steps.map((step) => (
                <li key={step.id}>
                  <p className="step-text">
                    {step.label}
                    {step.optional && <span className="muted"> (optional)</span>}
                    {step.out_of_scope && (
                      <span className="muted"> (out of scope for now)</span>
                    )}
                  </p>
                </li>
              ))}
            </ol>
          </details>
        </li>
      ))}
    </ol>
  );
}
