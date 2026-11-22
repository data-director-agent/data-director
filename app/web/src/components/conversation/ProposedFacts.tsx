/**
 * What a delegated run proposed about the project, said where the person reads the run: a few of
 * the facts in words, and a link that lands on them on the project's facts page. A proposal is
 * decided only there (docs/specs/app.md), so nothing here confirms anything; it only shows the
 * way. A run in no project has no facts page, so its proposals are listed with no link.
 */

import { type ProjectFact, factKey } from "../../project/facts";
import { factsPath, Link } from "../../route";
import { KIND_LABELS, describeFact } from "../project/factWording";

/** How many proposals are listed before the rest are counted. */
const LISTED = 3;

export function ProposedFacts({ facts, projectId }: { facts: readonly ProjectFact[]; projectId: string | null }) {
  if (facts.length === 0) return null;
  const listed = facts.slice(0, LISTED);
  const more = facts.length - listed.length;
  return (
    <div className="proposed-facts">
      <p>
        <strong>{facts.length === 1 ? "Proposed a fact" : `Proposed ${facts.length} facts`} for you to confirm</strong>
      </p>
      <ul>
        {listed.map((fact) => (
          <li key={factKey(fact)}>
            {KIND_LABELS[fact.fact_kind]}: {describeFact(fact)}
          </li>
        ))}
        {more > 0 && <li>and {more} more</li>}
      </ul>
      {projectId && (
        <p>
          <Link className="button button-secondary button-small" to={factsPath(projectId, facts.map(factKey))}>
            Review {facts.length === 1 ? "it" : "them"} in Project facts
          </Link>
        </p>
      )}
    </div>
  );
}
