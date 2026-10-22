/**
 * Beside the conversation: the delegated run the researcher opened, with its progress, outcome
 * and evidence (`RunPanel`), or, with none open, what the orchestrator is and how far to rely
 * on it (checklist item 9). Drawn from the manifest; a limit nobody declared is shown as not
 * declared.
 */

import type { ReactNode } from "react";

import type { AgentView } from "../../manifest/normalise";
import { GROUNDING } from "../../manifest/wording";
import { Link } from "../../route";
import { Models } from "../capabilities/CapabilitiesPanel";
import { IssueLinks } from "../NotBuilt";

export function ContextPanel({
  run,
  orchestrator,
}: {
  /** The open run's panel, or nothing when no run is open. */
  run: ReactNode;
  orchestrator: AgentView | undefined;
}) {
  if (run) return <div className="workspace-context">{run}</div>;
  return (
    <section aria-labelledby="context-heading" className="workspace-context">
      <h2 id="context-heading">Runs and evidence</h2>
      <p>
        When Data Director passes work to another agent, the conversation shows it as a card.
        Open one to see its progress, outcome and the evidence it rests on here.
      </p>
      {orchestrator && <AgentSummary agent={orchestrator} />}
    </section>
  );
}

function AgentSummary({ agent }: { agent: AgentView }) {
  const undeclared = Object.values(agent.oversight).every((v) => v.state === "undeclared");
  return (
    <>
      <h3>Who you are talking to</h3>
      <p>
        <code>
          {agent.id}@{agent.version}
        </code>
        : {agent.description}
      </p>
      <p>
        <strong>{GROUNDING[agent.groundingMode].label}.</strong>{" "}
        {GROUNDING[agent.groundingMode].explanation}
      </p>
      <Models models={agent.models} />
      {undeclared && (
        <p>
          <span className="status status-undeclared">Not declared</span> Its limits,
          reliability and handling of sensitive data (<IssueLinks issues={[67]} />).
        </p>
      )}
      <p>
        <Link to={`/agents?agent=${encodeURIComponent(agent.id)}`}>
          Its full capabilities and limits
        </Link>
      </p>
    </>
  );
}
