/**
 * What an agent uses besides a model, said the same way wherever an agent is shown: the MCP
 * servers it calls through the harness's tool gateway, with the tools it calls on each, and the
 * Agent Skills it may load. All of it is read from the agent's manifest. Digests and the rest of
 * the declaration stay in the technical details.
 */

import type { AgentView } from "../../manifest/normalise";

type ToolFacts = Pick<AgentView, "skills" | "tools">;

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The short form, for a line beside an agent's name. Nothing when the agent uses neither. */
export function ToolTag({ agent }: { agent: ToolFacts }) {
  const parts = [
    agent.tools.length > 0 && count(agent.tools.length, "MCP server", "MCP servers"),
    agent.skills.length > 0 && count(agent.skills.length, "skill", "skills"),
  ].filter((part): part is string => part !== false);
  if (parts.length === 0) return null;
  return <span className="status status-ok">{parts.join(" · ")}</span>;
}

/** The full form: each MCP server with its tools, and each skill, or the absence of both. */
export function Tools({ agent }: { agent: ToolFacts }) {
  if (agent.tools.length === 0 && agent.skills.length === 0) {
    return <p>This agent uses no MCP servers or skills.</p>;
  }
  return (
    <>
      {agent.tools.length > 0 && (
        <>
          <p>
            <strong>MCP servers</strong>, called through the deployment's tool gateway:
          </p>
          <ul className="tool-list">
            {agent.tools.map((t) => (
              <li key={t.server}>
                <code>{t.server}</code>
                {t.tools.length > 0 && (
                  <>
                    :{" "}
                    {t.tools.map((name, i) => (
                      <span key={name}>
                        {i > 0 && ", "}
                        <code>{name}</code>
                      </span>
                    ))}
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {agent.skills.length > 0 && (
        <>
          <p>
            <strong>Skills</strong>, instructions it follows:
          </p>
          <ul className="tool-list">
            {agent.skills.map((s) => (
              <li key={s.name}>
                <code>{s.name}</code> {s.version}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
