/**
 * The project's FAIR feedback tab (docs/ui/fair-feedback.md, #433): the latest report on the
 * metadata record in full, every check by principle, and each report stored in the project, so
 * that improvement over the project shows. Feedback is asked for in a conversation, where the
 * orchestrator delegates it; this page says how, and when every check a draft can meet is met it
 * points on to the deposit checks.
 */

import { useProjectApi } from "../../project/api";
import { ASK_FOR_FEEDBACK, readyForDeposit } from "../../project/fairness";
import { Link, projectTabPath } from "../../route";
import { useResource } from "../../useResource";
import { FairnessHistory } from "./FairnessHistory";
import { FairnessStanding } from "./FairnessStanding";
import { useFairnessHistory } from "./useFairnessHistory";

const HEADING_ID = "fair-heading";

export function FairnessPanel({ projectId }: { projectId: string }) {
  const api = useProjectApi();
  const history = useFairnessHistory(projectId);
  const documents = useResource(projectId, (id, signal) =>
    api.documents(id, signal),
  ).resource;
  const latest = history.state === "loaded" ? history.value[0] : undefined;
  return (
    <section className="fair-panel" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>FAIR feedback</h2>
      <p className="hint">
        How the project&apos;s draft metadata record does against a short list
        of checks tied to the FAIR principles (Findable, Accessible,
        Interoperable, Reusable), and what to improve next. Each improvement
        shows here. The checks are not a FAIRness evaluation, and they change
        nothing: you edit or approve the record.
      </p>
      <FairnessStanding
        history={history}
        documents={
          documents.state === "loaded" ? documents.value.documents : []
        }
      />
      <p>
        To check again, ask in{" "}
        <Link to="/">this project&apos;s conversations</Link>: “
        {ASK_FOR_FEEDBACK}”
      </p>
      {latest && readyForDeposit(latest.report) && (
        <p>
          Next:{" "}
          <Link to={projectTabPath(projectId, "deposit")}>
            the deposit checks
          </Link>
          .
        </p>
      )}
      {history.state === "loaded" && (
        <FairnessHistory history={history.value} />
      )}
    </section>
  );
}
