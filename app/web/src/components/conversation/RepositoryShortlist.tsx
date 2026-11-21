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
import type {
  ShortlistedRepository,
  UnlistedRepository,
} from "../../project/shortlist";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { registryRecord } from "../../project/registry";

const DOCUMENT_NAMES: Record<string, string> = {
  metadata_record: "a metadata record",
  readme: "a README",
  data_dictionary: "a data dictionary",
};

function documents(kinds: string[]): string {
  const named = kinds.map((k) => DOCUMENT_NAMES[k] ?? k);
  return named.length < 2
    ? (named[0] ?? "")
    : `${named.slice(0, -1).join(", ")} and ${named.at(-1)}`;
}

/** What a choice resolved to, in words. */
export function RepositoryRequirementsView({
  requirements,
}: {
  requirements: RepositoryRequirements;
}) {
  const required = requirements.fields.filter(
    (f) => f.obligation === "required",
  );
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
        <p>
          It should also have {documents(requirements.recommended_documents)}.
        </p>
      )}
      {required.length > 0 && (
        <p>
          Its metadata must give:{" "}
          {required.map((f) => f.form_label ?? f.property).join(", ")}.
        </p>
      )}
      {requirements.warnings.length > 0 && (
        <ul
          className="plain-list repository-warnings"
          aria-label="What this choice does not check"
        >
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

/** Why a repository is on the card, where it is not simply recommended. */
function Basis({ basis }: { basis: string | null }) {
  if (basis === "mandated")
    return <span className="status status-warn">Mandated</span>;
  if (basis === "asked_about")
    return <span className="status">You asked about this</span>;
  if (basis === "in_plan") return <span className="status">In your plan</span>;
  return null;
}

/** What re3data says of a deposit fee. It has no value for "no fee", so one it does not list is
 * one the repository has not stated, never one it does not charge (#1334). */
export function feeWording(fee: string | null): string | null {
  if (fee === "yes")
    return "A deposit fee is listed; re3data gives no amount, so check it with the repository.";
  if (fee === "unstated")
    return "Deposit fee: not stated by the repository, check with them.";
  return null;
}

export function RepositoryShortlist({
  projectId,
  shortlist,
  unlisted = [],
  planAttached = false,
  chosenId,
  idPrefix,
  onChosen,
}: {
  projectId: string;
  shortlist: ShortlistedRepository[];
  /** Repositories named that re3data does not list, shown as named and not to be chosen here. */
  unlisted?: UnlistedRepository[];
  /** Whether the researcher attached a document by this turn, which may be their plan. */
  planAttached?: boolean;
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
    setPending(repository.repositoryId);
    setError(null);
    try {
      const requirements = await projectApi.chooseRepository(
        projectId,
        repository.repositoryId,
      );
      setResolved(requirements);
      onChosen(requirements);
    } catch (e) {
      setError(
        `Data Director could not record ${repository.name} as your repository: ${errorMessage(e)}`,
      );
    } finally {
      setPending(null);
    }
  }

  const current = resolved?.repository_id ?? chosenId;
  return (
    <section
      className="callout repository-shortlist"
      aria-labelledby={headingId}
    >
      <h3 id={headingId}>Repositories shortlisted</h3>
      <p className="hint">
        Choose the one to deposit in. You can change it later.
      </p>
      <ul
        className="plain-list repository-candidates"
        aria-labelledby={headingId}
      >
        {shortlist.map((repository) => {
          const chosen = repository.repositoryId === current;
          return (
            <li
              key={repository.repositoryId}
              {...(chosen ? { "aria-current": "true" as const } : {})}
            >
              <p>
                <strong>{repository.name}</strong>{" "}
                <Basis basis={repository.basis} />{" "}
                {chosen && <span className="status status-ok">Chosen</span>}
                <br />
                <span className="hint">
                  {registryRecord(repository.repositoryId).registry}{" "}
                  {repository.uri ? (
                    <a href={repository.uri}>{repository.repositoryId}</a>
                  ) : (
                    <code>{repository.repositoryId}</code>
                  )}
                </span>
              </p>
              {repository.rationale && <p>{repository.rationale}</p>}
              {feeWording(repository.feeRequired) && (
                <p className="hint">{feeWording(repository.feeRequired)}</p>
              )}
              {!chosen && (
                <Button
                  size="small"
                  icon={Check}
                  isDisabled={pending !== null}
                  aria-label={`${pending === repository.repositoryId ? "Choosing" : "Choose"} ${repository.name}`}
                  onPress={() => void choose(repository)}
                >
                  {pending === repository.repositoryId ? "Choosing…" : "Choose"}
                </Button>
              )}
            </li>
          );
        })}
        {unlisted.map((repository) => (
          <li key={`unlisted-${repository.name}`}>
            <p>
              <strong>{repository.name}</strong>{" "}
              <Basis basis={repository.basis} />
              <br />
              <span className="hint">
                Not listed in re3data or DataCite, so nothing is shown of its
                terms, fees or identifiers: check them with the repository.
              </span>
            </p>
          </li>
        ))}
      </ul>
      {planAttached &&
        !unlisted.some((r) => r.basis === "in_plan") &&
        !shortlist.some((r) => r.basis === "in_plan") && (
          <p className="hint">
            If a document you attached is your data management plan, the
            repositories it names are shown here as &ldquo;In your plan&rdquo;
            once you confirm its sharing commitments on the project&apos;s
            documents page.
          </p>
        )}
      {error && (
        <p role="alert" className="callout status-danger">
          {error}
        </p>
      )}
      <div role="status">
        {resolved && (
          <div className="repository-resolved">
            <p>
              <strong>{resolved.repository_name}</strong> is the project&apos;s
              repository.
            </p>
            <RepositoryRequirementsView requirements={resolved} />
          </div>
        )}
      </div>
    </section>
  );
}
