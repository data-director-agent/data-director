/**
 * One agent as an end user needs to know it: its name, what it does, what it takes and returns,
 * what powers it and whether this deployment will run it. There is nothing to run here: a person
 * works with agents through the conversation, and the detail of how one behaves is for the
 * workbench.
 */

import "./AgentDetail.css";

import type { AgentView } from "../../manifest/normalise";
import { CapabilitiesPanel } from "../capabilities/CapabilitiesPanel";

export function AgentDetail({ agent }: { agent: AgentView }) {
  const headingId = `agent-${agent.id}-heading`;
  return (
    <section className="agent-detail" aria-labelledby={headingId}>
      <h2 id={headingId}>{agent.title ?? <code>{agent.id}</code>}</h2>
      <p>{agent.description}</p>
      <CapabilitiesPanel agent={agent} />
    </section>
  );
}
