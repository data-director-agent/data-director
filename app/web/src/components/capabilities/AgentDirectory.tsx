/**
 * Every registered agent, one selected at a time, with its general information beside the list. The list is a React Aria listbox: arrow keys move, and the selection follows
 * focus.
 *
 * When the profile names an orchestrator, the agent a person talks to, it is pinned first in a
 * section of its own, apart from the agents it hands work to behind the scenes. Without one the
 * list is flat.
 */

import "./AgentDirectory.css";

import { useState } from "react";
import {
  Header,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  type Selection,
} from "react-aria-components";

import { type AgentView, agentName, type Directory } from "../../manifest/normalise";
import { AgentDetail } from "../agent/AgentDetail";
import { ModelTag } from "./ModelDisclosure";

/** The section heading over the orchestrator. */
export const FRONT_SECTION = "You talk to";
/** The section heading over the agents it delegates to. */
export const BEHIND_SECTION = "Works behind the scenes";

function AgentOption({ agent, orchestrator }: { agent: AgentView; orchestrator?: boolean }) {
  return (
    <ListBoxItem
      id={agent.id}
      textValue={agentName(agent)}
      className={orchestrator ? "agent-option agent-option-orchestrator" : "agent-option"}
    >
      <span className="agent-option-title">{agentName(agent)}</span>
      {orchestrator && <span className="status agent-role">Orchestrator</span>}
      {orchestrator && " "}
      <ModelTag agent={agent} />
    </ListBoxItem>
  );
}

export function AgentDirectory({
  directory,
  initial,
  ownAccounts = false,
}: {
  directory: Directory;
  initial?: string | undefined;
  /** Whether this deployment lets the signed-in person use their own AI account. */
  ownAccounts?: boolean;
}) {
  const orchestrator = directory.agents.find((a) => a.id === directory.orchestratorId);
  const behind = directory.agents.filter((a) => a !== orchestrator);

  const first =
    directory.agents.find((a) => a.id === initial)?.id ??
    orchestrator?.id ??
    directory.agents[0]?.id;
  const [selected, setSelected] = useState<string | undefined>(first);
  const agent = directory.agents.find((a) => a.id === selected);

  return (
    <>
      {directory.unregistered.map((u) => (
        <div key={u.name} role="alert" className="callout status-danger">
          <p>
            <strong>
              {u.state === "unavailable" ? "Agent unavailable" : "Agent incompatible"}:
            </strong>{" "}
            <code>{u.name}</code> could not be registered. {u.reason}
          </p>
        </div>
      ))}
      {directory.agents.length === 0 ? (
        <p>No agents are registered with this deployment.</p>
      ) : (
        <div className="agents-layout">
          <div>
            <h2 id="agent-list-heading">Agents</h2>
            <ListBox
              aria-labelledby="agent-list-heading"
              className="agent-list"
              selectionMode="single"
              disallowEmptySelection
              selectionBehavior="replace"
              selectedKeys={selected === undefined ? [] : [selected]}
              onSelectionChange={(keys: Selection) => {
                if (keys !== "all") setSelected([...keys][0] as string | undefined);
              }}
            >
              {orchestrator ? (
                <>
                  <ListBoxSection id="front" className="agent-section">
                    <Header className="agent-section-header">{FRONT_SECTION}</Header>
                    <AgentOption agent={orchestrator} orchestrator />
                  </ListBoxSection>
                  {behind.length > 0 && (
                    <ListBoxSection id="behind" className="agent-section agent-section-behind">
                      <Header className="agent-section-header">{BEHIND_SECTION}</Header>
                      {behind.map((a) => (
                        <AgentOption key={a.id} agent={a} />
                      ))}
                    </ListBoxSection>
                  )}
                </>
              ) : (
                directory.agents.map((a) => <AgentOption key={a.id} agent={a} />)
              )}
            </ListBox>
          </div>
          {agent && (
            <AgentDetail
              key={agent.id}
              agent={agent}
              orchestrator={orchestrator}
              behindSection={behind.length > 0 ? BEHIND_SECTION : undefined}
              ownAccounts={ownAccounts}
            />
          )}
        </div>
      )}
    </>
  );
}
