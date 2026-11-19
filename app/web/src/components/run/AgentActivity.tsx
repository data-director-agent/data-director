/**
 * Under the Agent stage: what the agent has done so far (each delegated child and each tool call,
 * newest last, the most recent few) and, once the stream has been quiet for a while, a line saying
 * it is still working. Each row's mark and word carry its state, never colour alone; the run's
 * announcements say each start once (`run/announce.ts`), so this is not a live region.
 */

import { AGENT_ACTIVITY, STAGE_STATE } from "../../manifest/wording";
import { type ActivityItem, agentActivity } from "../../run/agentActivity";
import type { RunState } from "../../run/reduce";
import { useSince } from "./useSince";

/** The most recent rows shown; earlier ones are counted. */
export const SHOWN = 5;
/** How long the stream is quiet, while the agent runs, before the page says it is still working. */
export const QUIET_MS = 20_000;

const MARK = { running: "●", done: "✓", failed: "✗" } as const;

function Row({ item }: { item: ActivityItem }) {
  const verb = AGENT_ACTIVITY[item.kind][item.state];
  const outcome = item.state === "done" && item.status ? item.status : null;
  return (
    <li className={`activity activity-${item.state}`}>
      <span className="stage-mark" aria-hidden="true">
        {MARK[item.state]}
      </span>
      <span>
        {verb} <code>{item.name || "another agent"}</code>
        {item.state === "running" && "…"}
        {outcome && <span className="stage-state"> ({outcome})</span>}
        {item.state === "failed" && (
          <span className="status status-danger"> {STAGE_STATE.failed.label}</span>
        )}
      </span>
    </li>
  );
}

export function AgentActivity({ run, running }: { run: RunState; running: boolean }) {
  const items = agentActivity(run);
  const quietFor = useSince(run.log.length, running);
  const shown = items.slice(-SHOWN);
  const earlier = items.length - shown.length;
  if (shown.length === 0 && !(running && quietFor >= QUIET_MS)) return null;
  return (
    <div className="agent-activity">
      {shown.length > 0 && (
        <ol aria-label="What the agent has done">
          {earlier > 0 && <li className="muted">{AGENT_ACTIVITY.earlier(earlier)}</li>}
          {shown.map((item) => (
            <Row key={item.key} item={item} />
          ))}
        </ol>
      )}
      {running && quietFor >= QUIET_MS && <p className="muted">{AGENT_ACTIVITY.quiet}</p>}
    </div>
  );
}
