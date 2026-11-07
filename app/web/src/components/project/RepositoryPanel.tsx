/**
 * The repository chosen for a project, and what the harness resolved it to (docs/specs/deposit.md):
 * the requirement sets by version and digest, the warnings from resolving it, and the fields and
 * documents a package for it must or should have. The panel shows them as they are; whether a
 * package meets them is the deposit check's to say.
 *
 * A repository is chosen from `advisor.repository`'s shortlist in a conversation in this project,
 * so the panel says how, rather than offering a form to type one. Choosing again changes it: the
 * last choice counts. The panel reads the choice again whenever `revision` changes.
 */

import { useEffect, useState } from "react";

import { type RecordedPrincipal, type RepositoryChoice, useProjectApi } from "../../project/api";
import { Link } from "../../route";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: RepositoryChoice | null };

const HEADING_ID = "repository-heading";

const DOCUMENT_KINDS: Record<string, string> = {
  readme: "README",
  data_dictionary: "Data dictionary",
  metadata_record: "Metadata record",
  dmp: "Data management plan",
};

function kindName(kind: string): string {
  return DOCUMENT_KINDS[kind] ?? kind.replace(/_/g, " ");
}

function who(principal: RecordedPrincipal): string {
  return principal.name;
}

function Fields({ choice, obligation }: { choice: RepositoryChoice; obligation: string }) {
  const fields = (choice.requirements?.fields ?? []).filter((f) => f.obligation === obligation);
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

function Chosen({ choice }: { choice: RepositoryChoice }) {
  const requirements = choice.requirements;
  return (
    <>
      <dl className="facts">
        <dt>Repository</dt>
        <dd>
          <a href={`https://www.re3data.org/repository/${encodeURIComponent(choice.re3data_id)}`}>
            {choice.repository_name}
          </a>{" "}
          <span className="muted">
            (<code>{choice.re3data_id}</code>)
          </span>
        </dd>
        <dt>Chosen by</dt>
        <dd>
          {who(choice.chosen_by)}, <time dateTime={choice.chosen_at}>{choice.chosen_at}</time>
        </dd>
        <dt>Checked against</dt>
        <dd>
          {choice.requirement_sets.map((s, i) => (
            <span key={s.ref}>
              {i > 0 && ", "}
              <code>{s.ref}</code>
            </span>
          ))}
        </dd>
        {choice.declared_standards.length > 0 && (
          <>
            <dt>Standards re3data lists</dt>
            <dd>{choice.declared_standards.join(", ")}</dd>
          </>
        )}
      </dl>
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
      {requirements && (
        <>
          <h3>Documents</h3>
          <dl className="facts">
            <dt>Required</dt>
            <dd>{requirements.required_documents.map(kindName).join(", ") || "None"}</dd>
            <dt>Recommended</dt>
            <dd>{requirements.recommended_documents.map(kindName).join(", ") || "None"}</dd>
          </dl>
          <h3>Metadata the record must have</h3>
          <Fields choice={choice} obligation="required" />
          <h3>Metadata the record should have</h3>
          <Fields choice={choice} obligation="recommended" />
          {requirements.licences && requirements.licences.length > 0 && (
            <>
              <h3>Licences the repository offers</h3>
              <p>{requirements.licences.join(", ")}</p>
            </>
          )}
        </>
      )}
    </>
  );
}

export function RepositoryPanel({ projectId, revision }: { projectId: string; revision: number }) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api.repository(projectId, controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setLoad({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision]);

  const content = () => {
    if (load.state === "loading") return <p>Reading the chosen repository…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the chosen repository: {load.message}</p>
        </div>
      );
    }
    if (load.value === null) {
      return (
        <p>
          No repository has been chosen yet. Ask for a repository in{" "}
          <Link to="/">this project&apos;s conversations</Link>, then choose one from the
          shortlist.
        </p>
      );
    }
    return <Chosen choice={load.value} />;
  };

  return (
    <section className="repository" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Repository</h2>
      <p className="hint">
        The package is checked against what this repository asks for. To change it, choose another
        from a shortlist; the last choice counts.
      </p>
      {content()}
    </section>
  );
}
