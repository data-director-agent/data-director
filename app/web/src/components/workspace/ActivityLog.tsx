/**
 * The activity log: every step of every run in this conversation, as it happens. It needs runs
 * to stream their plan and steps over AG-UI (#68, #69), so it is drawn as not built. The
 * "thinking window" of the agents' exchanges would be a view of the same stream.
 */

import { NotBuilt } from "../NotBuilt";

export function ActivityLog() {
  return (
    <section aria-labelledby="activity-heading" className="workspace-log">
      <h2 id="activity-heading">Activity log</h2>
      <NotBuilt title="Each step of each run, as it happens" issues={[68, 69]}>
        <p>
          Until then, open a delegated run from the conversation to see its stages and outcome once
          it has ended.
        </p>
      </NotBuilt>
    </section>
  );
}
