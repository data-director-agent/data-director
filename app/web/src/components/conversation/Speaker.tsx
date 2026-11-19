/**
 * Who a part of the conversation is from, as a line over it: the person, or an agent by the name a
 * researcher sees. Kept apart from `Transcript` so `Pending` heads the part it shows the same way.
 */

import { AgentIcon, type AgentView, agentName } from "../../manifest/normalise";

/** The icon beside "You", in the place an agent's card icon takes. */
const PERSON_ICON = "👤";

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
 * Who a turn's part is from, by name alone. With no agent it is the person, "You". An agent is its
 * card's icon and title, or its id when the directory does not list it or its card names none. Its
 * version and what powers it are on the agent page, not in the conversation (docs/specs/app.md).
 */
export function Speaker({ agents = [], agentId }: { agents?: AgentView[]; agentId?: string }) {
  if (agentId === undefined) {
    return (
      <p className="turn-speaker">
        <strong className="turn-speaker-name">
          <span className="person-icon" aria-hidden="true">
            {PERSON_ICON}
          </span>
          You
        </strong>
      </p>
    );
  }
  const name = nameOf(agents, agentId);
  return (
    <p className="turn-speaker">
      <strong className="turn-speaker-name">
        <AgentIcon agent={{ icon: iconOf(agents, agentId) }} />
        {name === agentId ? <code>{agentId}</code> : name}
      </strong>
    </p>
  );
}
