/** The agents a harness may invoke (its `manifest/v0` extension), each folded under its name. */

import { agentName, readAgentSpec } from "../../spec/read";
import { AgentSpecView } from "./AgentSpecView";
import { None } from "./parts";

export function ManifestView({ agents, idPrefix }: { agents: readonly unknown[]; idPrefix: string }) {
  if (agents.length === 0) return <None />;
  return (
    <ul className="dd-items dd-manifest" aria-label="Agents">
      {agents.map((raw, i) => {
        const spec = readAgentSpec(raw);
        return (
          <li key={`${idPrefix}-${spec?.id ?? i}`}>
            {spec ? (
              <details>
                <summary>
                  <strong>{agentName(spec)}</strong>
                  {spec.title && <code className="dd-muted"> {spec.id}</code>}{" "}
                  <span className="dd-muted">{spec.version}</span>
                </summary>
                <p>{spec.description}</p>
                <AgentSpecView spec={spec} />
              </details>
            ) : (
              <span className="dd-issue">Agent {i + 1} is not a readable agent specification.</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
