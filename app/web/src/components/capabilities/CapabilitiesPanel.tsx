/**
 * Capabilities and limits: what one agent can do, how it grounds its results, and what this
 * deployment allows it, drawn entirely from its manifest (checklist items 9 and 2).
 *
 * Nothing here names an agent. A field the agent has not declared is shown as "Not declared",
 * and a reliability nobody has evaluated is shown as unsubstantiated.
 */

import type { AgentView, Declared, GateStatus } from "../../manifest/normalise";
import { DERIVATION, GROUNDING, className } from "../../manifest/wording";

const OVERSIGHT_FIELDS: { key: keyof AgentView["oversight"]; label: string }[] = [
  { key: "actions", label: "What it may change" },
  { key: "limits", label: "Limits" },
  { key: "reliability", label: "Reliability" },
  { key: "outcomes", label: "Outcomes it may return" },
  { key: "dataSensitivity", label: "How it handles sensitive data" },
];

export function CapabilitiesPanel({ agent }: { agent: AgentView }) {
  const headingId = `agent-${agent.id}-heading`;
  return (
    <section className="panel" aria-labelledby={headingId}>
      <h2 id={headingId}>
        <code>{agent.id}</code>
      </h2>
      <p>{agent.description}</p>
      <dl className="facts">
        <dt>Takes</dt>
        <dd>{agent.accepts.map(className).join(", ")}</dd>
        <dt>Returns</dt>
        <dd>
          {agent.payload === null
            ? "No result: it only reports an outcome"
            : className(agent.payload)}
        </dd>
        <dt>Version</dt>
        <dd>
          {agent.version} (contract {agent.contractVersion})
        </dd>
      </dl>

      <h3>Can this deployment run it?</h3>
      <Gate gate={agent.gate} />

      <h3>How it grounds its results</h3>
      <p>
        <strong>{GROUNDING[agent.groundingMode].label}.</strong>{" "}
        {GROUNDING[agent.groundingMode].explanation}
      </p>

      {agent.payload !== null && (
        <>
          <h3>How each field is produced</h3>
          {agent.derivations.length === 0 ? (
            <p>Every field is copied from your input or from the records it cites.</p>
          ) : (
            <>
              <p>Fields not listed here are copied from your input or from the records it cites.</p>
              <table className="derivations">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">How it is produced</th>
                  </tr>
                </thead>
                <tbody>
                  {agent.derivations.map((d) => (
                    <tr key={d.path}>
                      <td>
                        <code>{d.path}</code>
                      </td>
                      <td>{DERIVATION[d.how]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      <h3>Limits and reliability</h3>
      {OVERSIGHT_FIELDS.every(({ key }) => agent.oversight[key].state === "undeclared") && (
        <p>
          This agent does not declare its limits, its reliability or how it handles sensitive
          data. Treat its reliability as unsubstantiated.
        </p>
      )}
      <dl className="facts">
        {OVERSIGHT_FIELDS.map(({ key, label }) => (
          <OversightFact key={key} label={label} value={agent.oversight[key]} />
        ))}
      </dl>
    </section>
  );
}

function OversightFact({ label, value }: { label: string; value: Declared<unknown> }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {value.state === "undeclared" ? (
          <span className="status status-undeclared">Not declared</span>
        ) : (
          // TODO: render each declared field (increment 2, ADR-0025).
          <span>Declared</span>
        )}
      </dd>
    </>
  );
}

function Gate({ gate }: { gate: GateStatus }) {
  switch (gate.kind) {
    case "permitted":
      return (
        <div className="callout status-ok">
          <p>
            <span className="status status-ok">Permitted</span> This deployment's policy profile
            assigns it the action class <code>{gate.actionClass}</code>, which does not need
            approval.
          </p>
        </div>
      );
    case "needs-approval":
      return (
        <div className="callout status-warn">
          <p>
            <span className="status status-warn">Needs approval</span> This deployment's policy
            profile assigns it the action class <code>{gate.actionClass}</code>, which needs a
            data steward's approval. Runs are referred to a data steward and do not go ahead.
          </p>
        </div>
      );
    case "not-permitted":
      return (
        <div className="callout status-danger">
          <p>
            <span className="status status-danger">Not permitted</span> This deployment's policy
            profile does not list this agent, so Data Director refuses to run it.
          </p>
        </div>
      );
    case "mismatch":
      return (
        <div className="callout status-danger">
          <p>
            <span className="status status-danger">Refused</span> The agent declares the action
            class <code>{gate.declared}</code>, but this deployment's policy profile assigns it{" "}
            <code>{gate.assigned}</code>. Data Director refuses to run it until a data steward
            updates the profile.
          </p>
        </div>
      );
  }
}
