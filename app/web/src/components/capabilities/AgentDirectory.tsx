/**
 * Every registered agent, one selected at a time, with its detail (run, about, history)
 * beside the list. The list is a React Aria listbox: arrow keys move, and the selection follows
 * focus.
 */

import "./AgentDirectory.css";

import { useState } from "react";
import { ListBox, ListBoxItem, type Selection } from "react-aria-components";

import type { Directory } from "../../manifest/normalise";
import { AgentDetail } from "../agent/AgentDetail";

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
                <ListBoxItem id={a.id} textValue={a.id} className="agent-option">
                  <span className="agent-option-id">{a.id}</span>
                </ListBoxItem>
              )}
            </ListBox>
          </div>
          {agent && <AgentDetail key={agent.id} agent={agent} />}
        </div>
      )}
      {directory.unregistered.length > 0 && (
        <section aria-labelledby="unregistered-heading">
          <h2 id="unregistered-heading">Agents that could not be registered</h2>
          <ul>
            {directory.unregistered.map((u) => (
              <li key={u.name}>
                <code>{u.name}</code>{" "}
                <span className="status status-danger">
                  {u.state === "unavailable" ? "Unavailable" : "Incompatible"}
                </span>{" "}
                {u.reason}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
