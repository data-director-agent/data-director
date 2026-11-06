/**
 * Every registered agent, one selected at a time, with its general information beside the list. The list is a React Aria listbox: arrow keys move, and the selection follows
 * focus.
 */

import "./AgentDirectory.css";

import { useState } from "react";
import { ListBox, ListBoxItem, type Selection } from "react-aria-components";

import { agentName, type Directory } from "../../manifest/normalise";
import { AgentDetail } from "../agent/AgentDetail";
import { ModelTag } from "./ModelDisclosure";

export function AgentDirectory({
  directory,
  initial,
}: {
  directory: Directory;
  initial?: string | undefined;
}) {
  const first = directory.agents.find((a) => a.id === initial)?.id ?? directory.agents[0]?.id;
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
              items={directory.agents}
              selectionMode="single"
              disallowEmptySelection
              selectionBehavior="replace"
              selectedKeys={selected === undefined ? [] : [selected]}
              onSelectionChange={(keys: Selection) => {
                if (keys !== "all") setSelected([...keys][0] as string | undefined);
              }}
            >
              {(a) => (
                <ListBoxItem id={a.id} textValue={agentName(a)} className="agent-option">
                  <span className="agent-option-title">{agentName(a)}</span>
                  <br />
                  <ModelTag agent={a} />
                </ListBoxItem>
              )}
            </ListBox>
          </div>
          {agent && <AgentDetail key={agent.id} agent={agent} />}
        </div>
      )}
    </>
  );
}
