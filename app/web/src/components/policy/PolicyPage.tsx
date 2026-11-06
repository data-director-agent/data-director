/**
 * The policy page (`/policy`): the rules this deployment holds every run to, as the policy gate
 * holds them (docs/specs/policy-and-identity.md). The profile comes from `GET /api/policy`; each
 * agent's name and whether this deployment reaches it come from the agent directory. The page
 * draws both and decides nothing: whether an agent may run is the harness's answer.
 */

import "./PolicyPage.css";

import { useEffect, useState } from "react";

import type { AgentView, Directory } from "../../manifest/normalise";
import { type Policy, type PolicyAgent, usePolicyApi } from "../../policy/api";
import { Link } from "../../route";
import { PageHeader } from "../frame/PageHeader";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: Policy };

function nameOf(agentId: string, reached: Map<string, AgentView>): string {
  return reached.get(agentId)?.title || agentId;
}

/** What happens to a run of an agent the profile enables, as the directory reports it. */
function Status({
  entry,
  agent,
}: {
  entry: PolicyAgent;
  agent: AgentView | undefined;
}) {
  if (!agent) return <span className="status">Not reachable</span>;
  if (agent.gate.kind === "mismatch") {
    return (
      <>
        <span className="status status-danger">Refused</span> it declares{" "}
        <code>{agent.gate.declared}</code>
      </>
    );
  }
  return entry.requires_approval ? (
    <span className="status status-warn">Needs approval</span>
  ) : (
    <span className="status status-ok">Permitted</span>
  );
}

export function PolicyPage({ directory }: { directory: Directory }) {
  const api = usePolicyApi();
  const [state, setState] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api.get(controller.signal).then(
      (value) => setState({ state: "loaded", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          state: "failed",
          message: error instanceof Error ? error.message : String(error),
        });
      },
    );
    return () => controller.abort();
  }, [api]);

  const header = (
    <PageHeader title="Policy">
      <p className="hint">
        The rules this deployment holds every run to. A data steward sets them;
        Data Director checks each run against them before it starts, and every
        stored run names them.
      </p>
    </PageHeader>
  );

  if (state.state === "loading") {
    return (
      <>
        {header}
        <p role="status">Loading the policy…</p>
      </>
    );
  }
  if (state.state === "failed") {
    return (
      <>
        {header}
        <div role="alert" className="callout status-danger">
          <p>Data Director could not show its policy: {state.message}.</p>
        </div>
      </>
    );
  }

  const { profile, agents, actions_requiring_approval: approval } = state.value;
  const reached = new Map(directory.agents.map((agent) => [agent.id, agent]));
  const enabled = new Set(agents.map((entry) => entry.agent_id));
  const refused = directory.agents.filter((agent) => !enabled.has(agent.id));

  return (
    <>
      {header}
      <dl className="policy-details">
        <div>
          <dt>Profile</dt>
          <dd>
            <code>{profile.ref}</code>
          </dd>
        </div>
        <div>
          <dt>About it</dt>
          <dd>
            {profile.description || (
              <span className="muted">Not described</span>
            )}
          </dd>
        </div>
        <div>
          <dt>A conversation goes to</dt>
          <dd>
            {profile.orchestrator ? (
              nameOf(profile.orchestrator, reached)
            ) : (
              <span className="muted">
                No agent: this deployment offers no conversation
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Fingerprint (SHA-256)</dt>
          <dd>
            <code>{profile.digest}</code>
          </dd>
        </div>
      </dl>

      <section aria-labelledby="policy-agents">
        <h2 id="policy-agents">Agents it allows ({agents.length})</h2>
        <p>
          Each agent is allowed one action class, the kind of thing it may do.
          An agent that declares another class is refused.
        </p>
        {agents.length === 0 ? (
          <p className="muted">None: this policy allows no agent to run.</p>
        ) : (
          // A wide table scrolls within its own region rather than the page (WCAG 1.4.10 exempts
          // data tables); the region takes focus so it can be scrolled from the keyboard.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          <div
            className="table-scroll"
            role="region"
            aria-labelledby="policy-agents-caption"
            tabIndex={0}
          >
            <table className="data-table">
              <caption id="policy-agents-caption" className="visually-hidden">
                Each allowed agent, its action class and what happens to its
                runs here
              </caption>
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Action class</th>
                  <th scope="col">Here</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((entry) => {
                  const agent = reached.get(entry.agent_id);
                  return (
                    <tr key={entry.agent_id}>
                      <td>
                        {agent ? (
                          <Link
                            to={`/agents?agent=${encodeURIComponent(entry.agent_id)}`}
                          >
                            {nameOf(entry.agent_id, reached)}
                          </Link>
                        ) : (
                          entry.agent_id
                        )}
                        {agent?.title && (
                          <>
                            {" "}
                            <code className="muted">{entry.agent_id}</code>
                          </>
                        )}
                      </td>
                      <td>
                        <code>{entry.action_class}</code>
                      </td>
                      <td>
                        <Status entry={entry} agent={agent} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="policy-approval">
        <h2 id="policy-approval">
          Actions that need a data steward's approval
        </h2>
        {approval.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <>
            <p>
              A run of an agent with one of these action classes is referred to
              a data steward and does not go ahead on its own.
            </p>
            <ul>
              {approval.map((actionClass) => (
                <li key={actionClass}>
                  <code>{actionClass}</code>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {refused.length > 0 && (
        <section aria-labelledby="policy-refused">
          <h2 id="policy-refused">
            Agents it does not allow ({refused.length})
          </h2>
          <p>
            Data Director reaches these agents but this policy does not list
            them, so it refuses to run them.
          </p>
          <ul>
            {refused.map((agent) => (
              <li key={agent.id}>
                <Link to={`/agents?agent=${encodeURIComponent(agent.id)}`}>
                  {agent.title || agent.id}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
