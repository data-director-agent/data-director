/**
 * How FAIR the project's metadata record is so far, beside the conversation (docs/ui/fair-feedback.md):
 * the counts for each of F, A, I and R, what is new since the last check, what to do next with a
 * way to ask how, and a prompt to check again when the record has changed. A question goes in the
 * message box, unsent. Shown only where an agent in this deployment returns FAIR reports; the
 * shell knows that from the agents' payload classes, not their names.
 */

import type { ProjectDocument } from "../../../project/api";
import { Link, projectTabPath } from "../../../route";
import { FairnessStanding } from "../../fairness/FairnessStanding";
import { useFairnessHistory } from "../../fairness/useFairnessHistory";

export function FairFeedback({
  projectId,
  documents,
  refresh,
  onAsk,
}: {
  projectId: string;
  documents: readonly ProjectDocument[];
  refresh?: unknown;
  onAsk?: ((text: string) => void) | undefined;
}) {
  const history = useFairnessHistory(projectId, refresh);
  return (
    <section
      aria-labelledby="fair-pane-heading"
      className="pane-section fair-pane"
    >
      <h3 id="fair-pane-heading">How FAIR it is</h3>
      <FairnessStanding
        history={history}
        documents={documents}
        onAsk={onAsk}
        compact
      />
      <p className="pane-actions">
        <Link to={projectTabPath(projectId, "fair")}>Every check</Link>
      </p>
    </section>
  );
}
