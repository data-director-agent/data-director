/**
 * Who a part of the conversation is from, as a line over it: the person, or an agent by the name a
 * researcher sees. Kept apart from `Transcript` so `Pending` heads the part it shows the same way.
 */

import { CircleUserRound } from "lucide-react";

import { AgentIcon, type AgentView, agentName } from "../../manifest/normalise";
import { PERSON_ICONS, usePreferences } from "../../preferences";

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

/** The person who sent a turn: their name, and whether they are the one reading. */
export interface Sender {
  name: string;
  you: boolean;
}

/** Who sent a turn, from whom its run acted for, against who is reading (`viewer`); null when
 * the turn does not say. Until the reader is known, every turn is theirs, as it was before a
 * project had several members. */
export function senderOf(
  envelope: { acting_for?: { principal_id?: string; name: string } | null } | undefined,
  viewer: string | null,
): Sender | null {
  const by = envelope?.acting_for;
  if (!by) return null;
  const you = viewer === null || by.principal_id === undefined || by.principal_id === viewer;
  return { name: by.name, you };
}

/**
 * Who a turn's part is from, by name alone (the reader's own icon is the one they chose in Settings). With no agent it is a person: "You" for the one
 * reading, or one who sent nothing yet named; another member of the project by their name (#391). An agent is its
 * card's icon and title, or its id when the directory does not list it or its card names none. Its
 * version and what powers it are on the agent page, not in the conversation (docs/specs/app.md).
 */
export function Speaker({
  agents = [],
  agentId,
  person,
}: {
  agents?: AgentView[];
  agentId?: string;
  person?: Sender | null;
}) {
  const { personIcon } = usePreferences();
  if (agentId === undefined) {
    const you = !person || person.you;
    return (
      <p className="turn-speaker">
        <strong className="turn-speaker-name">
          {/* A neutral silhouette, as the account menu uses, in the place an agent's icon takes. */}
          <span className="person-icon" aria-hidden="true">
            {you && personIcon !== "person" ? (
              PERSON_ICONS[personIcon].icon
            ) : (
              <CircleUserRound size="1.125em" />
            )}
          </span>
          {you ? "You" : person.name}
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
