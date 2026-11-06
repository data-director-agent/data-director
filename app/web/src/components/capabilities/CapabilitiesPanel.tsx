/**
 * What one agent can do for a person and whether this deployment will run it, drawn from its
 * manifest. Nothing here names an agent. How it grounds results, how each field is produced, its
 * version and its oversight declarations are for the workbench, not for end users.
 */

import "./CapabilitiesPanel.css";

import type { AgentView, GateStatus } from "../../manifest/normalise";
import { className } from "../../manifest/wording";
import { Models } from "./ModelDisclosure";

export function CapabilitiesPanel({ agent }: { agent: AgentView }) {
  return (
    <div className="panel">
      <dl className="facts">
        <dt>Takes</dt>
        <dd>{agent.accepts.map(className).join(", ")}</dd>
        <dt>Returns</dt>
        <dd>
          {agent.payload === null
            ? "No result: it only reports an outcome"
            : className(agent.payload)}
        </dd>
      </dl>

      <h3>Can this deployment run it?</h3>
      <Gate gate={agent.gate} />

      <h3>What powers it, and what it is given</h3>
      <Models agent={agent} />
    </div>
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
