/**
 * Beside the conversation: the documents the project has produced, and what the orchestrator
 * is and how far to rely on it (checklist item 9). There is no record of the project yet
 * (#160), so its documents are drawn as not built rather than guessed at. The orchestrator's
 * summary is drawn from the manifest; a limit nobody declared is shown as not declared. A
 * delegated run and its evidence open in the transcript, beside the turn they support.
 */

import type { AgentView } from "../../manifest/normalise";
import { GROUNDING } from "../../manifest/wording";
import { Link } from "../../route";
import { Models } from "../capabilities/CapabilitiesPanel";
import { IssueLinks, NotBuilt } from "../NotBuilt";

export function ContextPanel({ orchestrator }: { orchestrator: AgentView | undefined }) {
  return (
    <section aria-labelledby="context-heading" className="workspace-context">
      <h2 id="context-heading">Project documents</h2>
      <NotBuilt title="The documents this project has produced" issues={[160]}>
        <p>
          READMEs, data dictionaries and metadata records will be listed here as agents draft
          them, each with the run it came from.
        </p>
      </NotBuilt>
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
