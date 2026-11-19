/**
 * The line Data Director draws at each Blueprint step under this policy (#448): whether the step
 * is delegated to an agent, needs approval, is never delegated or is not offered, and whom it is
 * referred to. The server works each step out from the profile and the agents serving it
 * (`GET /api/policy`); the shell draws it and decides nothing.
 */

import type { ReactNode } from "react";

import type { AgentView } from "../../manifest/normalise";
import type { PolicyStep } from "../../policy/api";
import { Link } from "../../route";

/** Whom a step is referred to, in a researcher's words. TODO(#373): from the profile. */
const REFERRED_TO: Record<string, string> = {
  data_steward: "A data steward",
};

function Autonomy({ step }: { step: PolicyStep }) {
  switch (step.autonomy) {
    case "delegated":
      return (
        <>
          <span className="status status-ok">Delegated</span>{" "}
          {step.action_classes.map((actionClass, i) => (
            <span key={actionClass}>
              {i > 0 && ", "}
              <code>{actionClass}</code>
            </span>
          ))}
        </>
      );
    case "must_approve":
      return <span className="status status-warn">Must approve</span>;
    case "never_delegated":
      return (
        <>
          <span className="status status-danger">Never delegated</span>{" "}
          <span className="hint">A person decides it.</span>
        </>
      );
    case "not_offered":
      return (
        <>
          <span className="status status-undeclared">Not offered</span>{" "}
          <span className="hint">
            {step.reason === "out_of_scope"
              ? "Out of scope for now."
              : "No agent here does it."}
          </span>
        </>
      );
  }
}

function Agents({
  step,
  reached,
}: {
  step: PolicyStep;
  reached: Map<string, AgentView>;
}): ReactNode {
  if (step.agent_ids.length === 0) return <span className="muted">None</span>;
  return step.agent_ids.map((agentId, i) => (
    <span key={agentId}>
      {i > 0 && ", "}
      <Link to={`/agents?agent=${encodeURIComponent(agentId)}`}>
        {reached.get(agentId)?.title || agentId}
      </Link>
    </span>
  ));
}

export function StepAutonomy({
  steps,
  reached,
}: {
  steps: PolicyStep[];
  reached: Map<string, AgentView>;
}) {
  const phases: { number: number; name: string; steps: PolicyStep[] }[] = [];
  for (const step of steps) {
    const last = phases.at(-1);
    if (last?.number === step.phase_number) last.steps.push(step);
    else
      phases.push({
        number: step.phase_number,
        name: step.phase_name,
        steps: [step],
      });
  }

  return (
    <section aria-labelledby="policy-steps">
      <h2 id="policy-steps">What it does at each step</h2>
      <p>
        Where Data Director draws the line at each step of the Blueprint: what
        it does with an agent, what it does only with a person's approval, what
        it leaves to people and what it does not offer. It is worked out from
        this policy and the agents that serve each step.
      </p>
      {steps.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <div
          className="table-scroll"
          role="region"
          aria-labelledby="policy-steps-caption"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
        >
          <table className="data-table">
            <caption id="policy-steps-caption" className="visually-hidden">
              Each step of the Blueprint, how far it is delegated here, the
              agents that serve it and whom it is referred to
            </caption>
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col">Here</th>
                <th scope="col">Agents</th>
                <th scope="col">Referred to</th>
              </tr>
            </thead>
            {phases.map((phase) => (
              <tbody key={phase.number}>
                <tr>
                  <th scope="rowgroup" colSpan={4}>
                    Phase {phase.number}: {phase.name}
                  </th>
                </tr>
                {phase.steps.map((step) => (
                  <tr key={step.step_id}>
                    <th scope="row">{step.label || step.step_id}</th>
                    <td>
                      <Autonomy step={step} />
                    </td>
                    <td>
                      <Agents step={step} reached={reached} />
                    </td>
                    <td>
                      {step.refers_to ? (
                        (REFERRED_TO[step.refers_to] ?? (
                          <code>{step.refers_to}</code>
                        ))
                      ) : (
                        <span className="muted">
                          {step.autonomy === "never_delegated"
                            ? "Not named in this policy"
                            : "No one"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </section>
  );
}
