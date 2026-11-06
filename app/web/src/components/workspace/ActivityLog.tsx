/**
 * The activity log, a page of its own in the main navigation: every step of every run, across
 * the person's conversations, as it happens. It needs runs to stream their plan and steps over
 * AG-UI (#68, #69), so it is drawn as not built. The "thinking window" of the agents' exchanges
 * would be a view of the same stream.
 */

import { PageHeader } from "../frame/PageHeader";
import { NotBuilt } from "../NotBuilt";

export function ActivityLog() {
  return (
    <>
      <PageHeader title="Activity log" />
      <NotBuilt title="Each step of each run, as it happens" issues={[68, 69]}>
        <p>
          Until then, open a delegated run from its card in a conversation to see its stages and
          outcome once it has ended.
        </p>
      </NotBuilt>
    </>
  );
}
