/**
 * Beside the conversation: the project it was started in, with the inventory the project holds
 * and a link to the documents agents have drafted in it (docs/specs/app.md), and what the
 * orchestrator is and how far to rely on it (checklist item 9). Listing the documents here, and
 * the rest of the project's record, is not built yet (#160). The orchestrator's summary is drawn
 * from the manifest; a limit nobody declared is shown as not declared. A delegated run and its
 * evidence open in the transcript, beside the turn they support.
 */

import { INVENTORY_GUIDE } from "../../conversation/inventory";
import type { Conversation } from "../../conversation/types";
import type { AgentView } from "../../manifest/normalise";
import { GROUNDING } from "../../manifest/wording";
import { Link } from "../../route";
import { Models } from "../capabilities/ModelDisclosure";
import { InventoryChip } from "../conversation/InventoryChip";
import { IssueLinks } from "../NotBuilt";

export function ContextPanel({
  orchestrator,
  conversation = null,
}: {
  orchestrator: AgentView | undefined;
  conversation?: Conversation | null;
}) {
  const projectId = conversation?.project_id;
  const inventory = conversation?.inventory;
  return (
    <section aria-labelledby="context-heading" className="workspace-context">
      <h2 id="context-heading">Project</h2>
      {projectId ? (
        <>
          {inventory ? (
            <p>
              <InventoryChip fileCount={inventory.file_count} madeAt={inventory.inventory_made_at} />
            </p>
          ) : (
            <p>
              No inventory of the dataset&apos;s files yet. Attach one to a message so that agents
              can describe the files. <a href={INVENTORY_GUIDE}>How do I make an inventory?</a>
            </p>
          )}
          <p>
            <Link to={`/projects/${encodeURIComponent(projectId)}`}>
              The documents drafted in this project
            </Link>
            , to approve, edit or reject.
          </p>
        </>
      ) : (
        <p>
          Your first message starts a project, which keeps the inventory you attach and the
          documents agents draft for you.
        </p>
      )}
      {orchestrator && <AgentSummary agent={orchestrator} />}
    </section>
  );
}

function AgentSummary({ agent }: { agent: AgentView }) {
  const undeclared = Object.values(agent.oversight).every((v) => v.state === "undeclared");
  return (
    <>
      <h3>Who you are talking to</h3>
      <p>
        {agent.title && <>{agent.title}, </>}
        <code>
          {agent.id}@{agent.version}
        </code>
        : {agent.description}
      </p>
      <p>
        <strong>{GROUNDING[agent.groundingMode].label}.</strong>{" "}
        {GROUNDING[agent.groundingMode].explanation}
      </p>
      <Models agent={agent} />
      {undeclared && (
        <p>
          <span className="status status-undeclared">Not declared</span> Its limits,
          reliability and handling of sensitive data (<IssueLinks issues={[67]} />).
        </p>
      )}
      <p>
        <Link to={`/agents?agent=${encodeURIComponent(agent.id)}`}>
          Its full capabilities and limits
        </Link>
      </p>
    </>
  );
}
