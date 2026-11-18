/**
 * Who a part of the conversation is from, as a line over it: the person, or an agent by the name a
 * researcher sees, with the details that identify it exactly beneath. Kept apart from
 * `Transcript` so `Pending` heads the part it shows the same way.
 */

import { AgentIcon, type AgentView, agentName } from "../../manifest/normalise";
import { ModelTag } from "../capabilities/ModelDisclosure";

/** The agent's name as a researcher sees it: its card's title, or its id when the directory does
 * not list it or its card names none. */
export function nameOf(agents: AgentView[], agentId: string): string {
  const agent = agents.find((a) => a.id === agentId);
  return agent ? agentName(agent) : agentId;
}

/** The icon the agent's card declares, or "" (the default) when the directory does not list it. */
export function iconOf(agents: AgentView[], agentId: string): string {
  return agents.find((a) => a.id === agentId)?.icon ?? "";
}

/**
 * Who a turn's part is from: a name, and beneath it the details that identify it exactly. With no
 * agent it is the person, "You", with no details. An agent is its name, with `id@version` and
 * what powers it beneath; when it has no name but its id, the id is the name and shown once.
 */
export function Speaker({
  agents = [],
  agentId,
  agentVersion,
}: {
  agents?: AgentView[];
  agentId?: string;
  agentVersion?: string;
}) {
  if (agentId === undefined) {
    return (
      <p className="turn-speaker">
        <strong className="turn-speaker-name">You</strong>
      </p>
    );
  }
  const agent = agents.find((a) => a.id === agentId);
  const name = agent ? agentName(agent) : agentId;
  const exact = agentVersion === undefined ? agentId : `${agentId}@${agentVersion}`;
  const named = name !== agentId;
  return (
    <p className="turn-speaker">
      <strong className="turn-speaker-name">
        <AgentIcon agent={{ icon: agent?.icon ?? "" }} />
        {named ? name : <code>{exact}</code>}
      </strong>
      {(named || agent) && (
        <span className="turn-speaker-details">
          {named && <code>{exact}</code>}
          {named && agent && " "}
          {agent && <ModelTag agent={agent} />}
        </span>
      )}
    </p>
  );
}
