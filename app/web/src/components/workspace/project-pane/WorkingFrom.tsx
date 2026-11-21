/**
 * What Data Director is working from: the project's facts that shape its answers, each marked
 * confirmed, proposed or not known, and the repository chosen. When one of them is wrong, the
 * person sees it beside the conversation before relying on an answer built on it
 * (docs/ui/best-practices.md §4). Facts are changed on the project facts page.
 */

import type { ProjectSummary } from "../../../project/api";
import type { FactKind, ProjectFacts } from "../../../project/facts";
import { Link, projectTabPath } from "../../../route";
import type { Resource } from "../../../useResource";
import { KIND_LABELS } from "../../project/factWording";
import { WORKING_KINDS, factValue } from "./facts";

type ChosenRepository = ProjectSummary["repository"];

/** Whether anything is known of `kind`: decided, or proposed and waiting. */
function known(kind: FactKind, facts: ProjectFacts): boolean {
  return facts.decisions.some((f) => f.fact_kind === kind) || facts.proposals.some((p) => p.fact.fact_kind === kind);
}

function FactRow({ kind, facts }: { kind: FactKind; facts: ProjectFacts }) {
  const decided = facts.decisions.filter((f) => f.fact_kind === kind);
  const proposed = facts.proposals.filter((p) => p.fact.fact_kind === kind);
  return (
    <div>
      <dt>{KIND_LABELS[kind]}</dt>
      <dd>
        {decided.length > 0 ? (
          <>
            {decided.map(factValue).join("; ")} <span className="status status-ok">Confirmed</span>
          </>
        ) : (
          <>
            {proposed.map((p) => factValue(p.fact)).join("; ")} <span className="status status-warn">Proposed</span>
          </>
        )}
      </dd>
    </div>
  );
}

/** The kinds nothing is known of, in one row, so that the list stays short. */
function UnknownRow({ kinds }: { kinds: FactKind[] }) {
  if (kinds.length === 0) return null;
  return (
    <div>
      <dt>Not known yet</dt>
      <dd>{kinds.map((kind) => KIND_LABELS[kind]).join(", ")}</dd>
    </div>
  );
}

function RepositoryRow({ repository }: { repository: ChosenRepository | undefined }) {
  return (
    <div>
      <dt>Repository chosen</dt>
      <dd>
        {repository ? (
          <>
            {repository.repository_name}{" "}
            {repository.warnings.length > 0 ? (
              <span className="status status-warn">
                {repository.warnings.length === 1 ? "1 warning" : `${repository.warnings.length} warnings`}
              </span>
            ) : (
              <span className="status status-ok">Chosen</span>
            )}
          </>
        ) : (
          <span className="hint">None chosen yet: ask which repositories suit the data</span>
        )}
      </dd>
    </div>
  );
}

export function WorkingFrom({
  projectId,
  repository,
  facts,
}: {
  projectId: string;
  repository: ChosenRepository | undefined;
  facts: Resource<ProjectFacts>;
}) {
  return (
    <section aria-labelledby="working-heading" className="pane-section">
      <h3 id="working-heading">What Data Director is working from</h3>
      <dl className="pane-facts">
        {facts.state === "loaded" && (
          <>
            {WORKING_KINDS.filter((kind) => known(kind, facts.value)).map((kind) => (
              <FactRow key={kind} kind={kind} facts={facts.value} />
            ))}
            <UnknownRow kinds={WORKING_KINDS.filter((kind) => !known(kind, facts.value))} />
          </>
        )}
        <RepositoryRow repository={repository} />
      </dl>
      {facts.state === "loading" && <p className="hint">Reading the project&apos;s facts…</p>}
      <p className="pane-actions">
        <Link to={projectTabPath(projectId, "facts")}>Check or change the facts</Link>
        <Link to={projectTabPath(projectId, "researchers")}>Researchers</Link>
      </p>
    </section>
  );
}
