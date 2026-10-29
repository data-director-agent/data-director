/**
 * One agent: its name and description over three tabs. Run is where a person gives it input and
 * reads what came back; About is what it can do and what this deployment allows (its manifest);
 * History is its stored runs.
 *
 * The tabs are React Aria Tabs: arrow keys move between them, and Run and History stay mounted
 * while hidden, so a run and an opened record survive a look at About.
 */

import "./AgentDetail.css";

import { useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";

import type { AgentView } from "../../manifest/normalise";
import { CapabilitiesPanel } from "../capabilities/CapabilitiesPanel";
import { ModelTag } from "../capabilities/ModelDisclosure";
import { RunHistory } from "../history/RunHistory";
import { RunView } from "../run/RunView";

export function AgentDetail({ agent }: { agent: AgentView }) {
  const headingId = `agent-${agent.id}-heading`;
  const [finished, setFinished] = useState(0);
  return (
    <section className="agent-detail" aria-labelledby={headingId}>
      <h2 id={headingId}>
        <code>{agent.id}</code>
      </h2>
      <p>{agent.description}</p>
      <p>
        <ModelTag agent={agent} />
      </p>
      <Tabs className="tabs" defaultSelectedKey="run">
        <TabList className="tab-list" aria-label={`${agent.id}: views`}>
          <Tab className="tab" id="run">
            Run
          </Tab>
          <Tab className="tab" id="about">
            About
          </Tab>
          <Tab className="tab" id="history">
            History
          </Tab>
        </TabList>
        <TabPanel className="tab-panel" id="run" shouldForceMount>
          <RunView agent={agent} onFinished={() => setFinished((n) => n + 1)} />
        </TabPanel>
        <TabPanel className="tab-panel" id="about">
          <CapabilitiesPanel agent={agent} embedded />
        </TabPanel>
        <TabPanel className="tab-panel" id="history" shouldForceMount>
          <RunHistory agent={agent} refresh={finished} />
        </TabPanel>
      </Tabs>
    </section>
  );
}
