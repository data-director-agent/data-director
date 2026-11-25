/**
 * The conversation page in a project its data steward opened (docs/specs/stewardship.md,
 * invariant 6, "Run an agent in the project"): a banner that cannot be dismissed says whose
 * project it is, that each run here acts for the steward and is recorded with their name, and
 * that what the agents draft is proposed for the project's owners to decide. Nothing renders for
 * a member of the project.
 */

import "./Steward.css";

import { ShieldCheck } from "lucide-react";

import { asSteward } from "../../project/steward";
import { useProjectView } from "../../project/view";
import { Link, projectTabPath } from "../../route";

export function StewardConversationBanner() {
  const { view } = useProjectView();
  if (!view || !asSteward(view)) return null;
  const title = view.title ?? "this project";
  return (
    <section className="callout status-warn steward-banner" aria-labelledby="steward-conversation-heading">
      <h2 id="steward-conversation-heading">
        <ShieldCheck size="1em" aria-hidden="true" /> Working as a data steward
      </h2>
      <p>
        You are asking the agents in {view.created_by.name}&apos;s project, {title}. Each run acts
        for you and is recorded with your name; what the agents draft is proposed for the
        project&apos;s owners to approve or reject.{" "}
        <Link to={projectTabPath(view.project_id)}>Back to the project</Link>
      </p>
    </section>
  );
}
