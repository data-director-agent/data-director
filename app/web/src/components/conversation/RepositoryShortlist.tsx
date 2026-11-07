/**
 * The repositories an advisor shortlisted on a turn, for the researcher to choose one
 * (docs/specs/deposit.md). Each names its repository as the re3data record the advisor cited; the
 * choice sends only that identifier, and the harness reads the repository's name and declared
 * metadata standards from the pinned re3data export. The card then shows what the choice resolved
 * to: the requirement sets used, what the deposit must have, and any warning of what is not
 * checked. Choosing another is a new choice, and the last one counts.
 */

import "./RepositoryShortlist.css";

import { Check } from "lucide-react";
import { useState } from "react";

import { type RepositoryRequirements, useProjectApi } from "../../project/api";
import type { ShortlistedRepository } from "../../project/shortlist";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";

const DOCUMENT_NAMES: Record<string, string> = {
  metadata_record: "a metadata record",
  readme: "a README",
  data_dictionary: "a data dictionary",
};

function documents(kinds: string[]): string {
  const named = kinds.map((k) => DOCUMENT_NAMES[k] ?? k);
  return named.length < 2 ? (named[0] ?? "") : `${named.slice(0, -1).join(", ")} and ${named.at(-1)}`;
}

/** What a choice resolved to, in words. */
export function RepositoryRequirementsView({ requirements }: { requirements: RepositoryRequirements }) {
  const required = requirements.fields.filter((f) => f.obligation === "required");
  return (
    <>
      <p>
        Checked against{" "}
        {requirements.requirement_sets.map((s, i) => (
          <span key={s.ref}>
            {i > 0 && " and "}
            <code>{s.ref}</code>
          </span>
        ))}
        .
      </p>
      {requirements.required_documents.length > 0 && (
        <p>A deposit needs {documents(requirements.required_documents)}.</p>
      )}
      {requirements.recommended_documents.length > 0 && (
        <p>It should also have {documents(requirements.recommended_documents)}.</p>
      )}
      {required.length > 0 && (
        <p>
          Its metadata must give: {required.map((f) => f.form_label ?? f.property).join(", ")}.
        </p>
      )}
      {requirements.warnings.length > 0 && (
        <ul className="plain-list repository-warnings" aria-label="What this choice does not check">
          {requirements.warnings.map((w) => (
            <li key={w}>
              <span className="status status-warn">Warning</span> {w}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function RepositoryShortlist({
  projectId,
  shortlist,
  chosenId,
  idPrefix,
  onChosen,
}: {
  projectId: string;
  shortlist: ShortlistedRepository[];
  /** The repository the project chose last, if any. */
  chosenId: string | null;
  /** Unique within the page, for the card's ids. */
  idPrefix: string;
  onChosen: (requirements: RepositoryRequirements) => void;
}) {
  const projectApi = useProjectApi();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<RepositoryRequirements | null>(null);
  const headingId = `${idPrefix}-heading`;

  async function choose(repository: ShortlistedRepository) {
    setPending(repository.re3dataId);
    setError(null);
    try {
      const requirements = await projectApi.chooseRepository(projectId, repository.re3dataId);
      setResolved(requirements);
      onChosen(requirements);
    } catch (e) {
      setError(`Data Director could not record ${repository.name} as your repository: ${errorMessage(e)}`);
    } finally {
      setPending(null);
    }
  }

  const current = resolved?.re3data_id ?? chosenId;
  return (
    <section className="callout repository-shortlist" aria-labelledby={headingId}>
      <h3 id={headingId}>Repositories shortlisted</h3>
      <p className="hint">Choose the one to deposit in. You can change it later.</p>
      <ul className="plain-list repository-candidates" aria-labelledby={headingId}>
        {shortlist.map((repository) => {
          const chosen = repository.re3dataId === current;
          return (
            <li key={repository.re3dataId} {...(chosen ? { "aria-current": "true" as const } : {})}>
              <p>
                <strong>{repository.name}</strong>{" "}
                {repository.basis === "mandated" && <span className="status status-warn">Mandated</span>}{" "}
                {chosen && <span className="status status-ok">Chosen</span>}
                <br />
                <span className="hint">
                  re3data{" "}
                  {repository.uri ? (
                    <a href={repository.uri}>{repository.re3dataId}</a>
                  ) : (
                    <code>{repository.re3dataId}</code>
                  )}
                </span>
              </p>
              {repository.rationale && <p>{repository.rationale}</p>}
              {!chosen && (
                <Button
                  size="small"
                  icon={Check}
                  isDisabled={pending !== null}
                  aria-label={`${pending === repository.re3dataId ? "Choosing" : "Choose"} ${repository.name}`}
                  onPress={() => void choose(repository)}
                >
                  {pending === repository.re3dataId ? "Choosing…" : "Choose"}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      {error && (
        <p role="alert" className="callout status-danger">
          {error}
        </p>
      )}
      <div role="status">
        {resolved && (
          <div className="repository-resolved">
            <p>
              <strong>{resolved.repository_name}</strong> is the project&apos;s repository.
            </p>
            <RepositoryRequirementsView requirements={resolved} />
          </div>
        )}
      </div>
    </section>
  );
}
