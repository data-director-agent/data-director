/**
 * What Data Director holds about the repository a project chose, as the Repository tab shows it
 * (docs/specs/app.md): where the repository is, what it accepts, what Data Director works from
 * (the warnings from resolving the choice and what its sets leave open), the documents and
 * metadata a package for it must or should have, and the pages the values were taken from.
 *
 * Everything comes from the merged requirement set the harness keeps for the choice, read from
 * the pinned re3data export and the deployment's sets; nothing is looked up live, so what is shown
 * is what the checks use. A value the sets do not state is not shown, never filled in here.
 */

import type { RepositoryRequirements } from "../../project/api";
import { sizeInWords } from "./DepositPanel";
import { Unconfirmed } from "./Unconfirmed";

const DOCUMENT_KINDS: Record<string, string> = {
  readme: "README",
  data_dictionary: "Data dictionary",
  metadata_record: "Metadata record",
  dmp: "Data management plan",
};

function kindName(kind: string): string {
  return DOCUMENT_KINDS[kind] ?? kind.replace(/_/g, " ");
}

function Fields({ choice, obligation }: { choice: RepositoryRequirements; obligation: string }) {
  const fields = choice.fields.filter((f) => f.obligation === obligation);
  if (fields.length === 0) return <p className="muted">None.</p>;
  return (
    <ul>
      {fields.map((f) => (
        <li key={`${f.property}-${f.schema_org}-${JSON.stringify(f.qualifier ?? {})}`}>
          {f.form_label ?? f.property}{" "}
          <span className="muted">
            (<code>{f.property}</code>)
          </span>
        </li>
      ))}
    </ul>
  );
}

function About({ choice }: { choice: RepositoryRequirements }) {
  return (
    <dl className="facts">
      <dt>Repository</dt>
      <dd>
        <a href={`https://www.re3data.org/repository/${encodeURIComponent(choice.re3data_id)}`}>
          {choice.repository_name}
        </a>{" "}
        <span className="muted">
          (<code>{choice.re3data_id}</code>, its re3data record)
        </span>
      </dd>
      {choice.repository_url && (
        <>
          <dt>Where to deposit</dt>
          <dd>
            <a href={choice.repository_url}>{choice.repository_url}</a>
          </dd>
        </>
      )}
      <dt>Checked against</dt>
      <dd>
        {choice.requirement_sets.map((s, i) => (
          <span key={s.ref}>
            {i > 0 && ", "}
            <code>{s.ref}</code>
          </span>
        ))}
      </dd>
    </dl>
  );
}

/** What the repository accepts, as far as its sets state it; nothing when they state nothing. */
function Accepts({ choice }: { choice: RepositoryRequirements }) {
  const types = choice.media_types ?? [];
  const licences = choice.licences ?? [];
  const stated =
    types.length > 0 ||
    licences.length > 0 ||
    choice.max_file_size !== undefined ||
    choice.max_item_size !== undefined;
  if (!stated) return null;
  return (
    <>
      <h3>What it accepts</h3>
      <dl className="facts">
        {types.length > 0 && (
          <>
            <dt>File types</dt>
            <dd>
              {types.map((t, i) => (
                <span key={t}>
                  {i > 0 && ", "}
                  <code>{t}</code>
                </span>
              ))}
            </dd>
          </>
        )}
        {choice.max_file_size !== undefined && (
          <>
            <dt>Largest file</dt>
            <dd>{sizeInWords(choice.max_file_size)}</dd>
          </>
        )}
        {choice.max_item_size !== undefined && (
          <>
            <dt>Largest item</dt>
            <dd>{sizeInWords(choice.max_item_size)}</dd>
          </>
        )}
        {licences.length > 0 && (
          <>
            <dt>Licences</dt>
            <dd>{licences.join(", ")}</dd>
          </>
        )}
      </dl>
    </>
  );
}

/** What Data Director works from for this repository, and what it cannot check. */
function Assumptions({ choice }: { choice: RepositoryRequirements }) {
  return (
    <>
      <h3>What Data Director assumes</h3>
      <ul>
        <li>
          The package is checked against the requirement sets above, as this deployment holds them,
          and nothing is looked up from {choice.repository_name} itself.
        </li>
        {/* TODO(#383): say so only for a repository without a `deposit` block, once sets have one. */}
        <li>
          You deposit the package yourself, in the repository: Data Director does not deposit
          through its API yet.
        </li>
      </ul>
      {choice.warnings.length > 0 && (
        <div className="callout status-warn">
          <p>
            <strong>Not everything this repository asks for can be checked:</strong>
          </p>
          <ul>
            {choice.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <Unconfirmed items={choice.unconfirmed ?? []} name={choice.repository_name} />
    </>
  );
}

function Sources({ choice }: { choice: RepositoryRequirements }) {
  const pages = choice.guidance ?? [];
  if (pages.length === 0) return null;
  return (
    <>
      <h3>Where this comes from</h3>
      <ul>
        {pages.map((page) => (
          <li key={page}>
            <a href={page}>{page}</a>
          </li>
        ))}
      </ul>
    </>
  );
}

export function RepositoryDetails({ choice }: { choice: RepositoryRequirements }) {
  return (
    <>
      <About choice={choice} />
      <Accepts choice={choice} />
      <Assumptions choice={choice} />
      <h3>Documents</h3>
      <dl className="facts">
        <dt>Required</dt>
        <dd>{choice.required_documents.map(kindName).join(", ") || "None"}</dd>
        <dt>Recommended</dt>
        <dd>{choice.recommended_documents.map(kindName).join(", ") || "None"}</dd>
      </dl>
      <h3>Metadata the record must have</h3>
      <Fields choice={choice} obligation="required" />
      <h3>Metadata the record should have</h3>
      <Fields choice={choice} obligation="recommended" />
      <Sources choice={choice} />
    </>
  );
}
