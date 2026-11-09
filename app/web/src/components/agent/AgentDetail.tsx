/**
 * One agent as an end user needs to know it: its name, what it does, what it takes and returns,
 * what powers it and whether this deployment will run it. There is nothing to run here: a person
 * works with agents through the conversation, and the detail of how one behaves is for the
 * workbench.
 *
 * When the deployment has an orchestrator, a line under the description says where the agent
 * sits: the one a person talks to, or one it calls on behind the scenes.
 *
 * Under it, folded away, is what the agent's card declares, field by field
 * (`@data-director/agent-view`'s `AgentSpecView`), for a data steward or developer who needs to
 * inspect it: the schemas, derivations and contract version that the rest of the page puts into
 * words.
 */

import "./AgentDetail.css";
import "@data-director/agent-view/styles.css";

import { AgentSpecView } from "@data-director/agent-view/react";

import { type AgentView, agentName } from "../../manifest/normalise";
import { CapabilitiesPanel } from "../capabilities/CapabilitiesPanel";

export function AgentDetail({
  agent,
  orchestrator,
  behindSection,
}: {
  agent: AgentView;
  /** The deployment's orchestrator, if it has one. */
  orchestrator?: AgentView | undefined;
  /** What the directory calls the section of agents behind the scenes, if it shows one. */
  behindSection?: string | undefined;
}) {
  const headingId = `agent-${agent.id}-heading`;
  return (
    <section className="agent-detail" aria-labelledby={headingId}>
      <h2 id={headingId}>{agent.title ?? <code>{agent.id}</code>}</h2>
      <p>{agent.description}</p>
      {orchestrator && (
        <p className="agent-role-note">
          {agent.id === orchestrator.id ? (
            <>
              This is the agent you talk to.
              {behindSection && (
                <>
                  {" "}
                  It hands work to the agents listed under <em>{behindSection}</em>.
                </>
              )}
            </>
          ) : (
            <>
              {agentName(orchestrator)} calls on this agent; you don’t talk to it directly.
            </>
          )}
        </p>
      )}
      <CapabilitiesPanel agent={agent} />
      <details className="agent-technical">
        <summary>Technical details: what its agent card declares</summary>
        <AgentSpecView spec={agent} withIdentity />
      </details>
    </section>
  );
}
