/**
 * An agent's icon, shown beside its name. Decorative: the name beside it says who the agent is,
 * so assistive technology skips it.
 */

import { type AgentSpec, agentIcon } from "../../spec/read";

export function AgentIcon({ agent }: { agent: Pick<AgentSpec, "icon"> }) {
  return (
    <span className="agent-icon" aria-hidden="true">
      {agentIcon(agent)}
    </span>
  );
}
