/**
 * What powers an agent, said the same way wherever an agent is shown: a language model (which
 * one, from whom, and whether it runs remotely or locally), or no model at all. All of it is
 * read from the agent's manifest, as configured; a manifest that does not say is shown as not
 * declared, never as deterministic.
 */

import type { AgentView } from "../../manifest/normalise";
import { HOSTING, PROVIDER } from "../../manifest/wording";

type ModelFacts = Pick<AgentView, "models" | "modelsDeclared">;

/** The short form, for a line beside an agent's name. */
export function ModelTag({ agent }: { agent: ModelFacts }) {
  if (!agent.modelsDeclared) {
    return <span className="status status-undeclared">AI model not declared</span>;
  }
  if (agent.models.length === 0) {
    return <span className="status status-ok">No AI model: deterministic</span>;
  }
  return (
    <>
      {agent.models.map((m) => (
        <span
          key={`${m.provider}/${m.model}`}
          className={`status ${m.hosting === "hosted" ? "status-warn" : "status-ok"}`}
        >
          Language model, {HOSTING[m.hosting].label.toLowerCase()}: <code>{m.model}</code>
        </span>
      ))}
    </>
  );
}

/** The full form: each model with its provider and where it runs, or the absence of one. */
export function Models({ agent }: { agent: ModelFacts }) {
  if (!agent.modelsDeclared) {
    return (
      <p>
        <span className="status status-undeclared">Not declared</span> This agent does not say
        whether it uses an AI model.
      </p>
    );
  }
  if (agent.models.length === 0) {
    return (
      <p>
        <strong>No AI model.</strong> This agent is deterministic software: it sends your input to
        no language model.
      </p>
    );
  }
  return (
    <ul>
      {agent.models.map((m) => (
        <li key={`${m.provider}/${m.model}`}>
          <strong>Language model, {HOSTING[m.hosting].label.toLowerCase()}:</strong>{" "}
          {PROVIDER[m.provider] ?? m.provider} <code>{m.model}</code>. As configured, it{" "}
          {HOSTING[m.hosting].explanation}, and your input is sent to it.
        </li>
      ))}
    </ul>
  );
}
