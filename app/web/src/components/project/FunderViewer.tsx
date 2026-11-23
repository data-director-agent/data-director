/**
 * One funder a project names: the fact as it stands or is proposed, and the organisation behind its
 * ROR identifier as the pinned ROR dump records it, so that a person deciding on a name and
 * identifier can see what they stand for (docs/specs/app.md).
 */

import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";

import {
  OrganisationNotFound,
  type RorOrganisation,
  displayName,
  useFundersApi,
} from "../../project/funders";
import { type ProjectFact, type ProjectFacts, factKey } from "../../project/facts";
import { factsPath, Link } from "../../route";
import { message, type PanelLoad } from "./panelLoad";
import { describeFact } from "./factWording";

const HEADING_ID = "funder-heading";

/** The funder facts of `facts` at `subject`: those that stand, and those proposed. */
function funderFacts(facts: ProjectFacts, subject: string) {
  const at = (fact: ProjectFact) => fact.fact_kind === "funder" && fact.fact_subject === subject;
  return {
    decided: facts.decisions.filter(at),
    proposed: facts.proposals.filter((proposal) => at(proposal.fact)),
  };
}

/** A Crossref Funder ID without its DOI prefix, which a person may or may not have typed. */
const bareFunderId = (id: string) => id.trim().replace(/^10\.13039\//, "");

function Names({ organisation }: { organisation: RorOrganisation }) {
  return (
    <ul>
      {organisation.names.map((name) => (
        <li key={`${name.value}|${name.types.join(",")}|${name.lang ?? ""}`}>
          {name.value}
          {(name.types.length > 0 || name.lang) && (
            <span className="hint">
              {" "}
              ({[...name.types, ...(name.lang ? [name.lang] : [])].join(", ")})
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function Organisation({ organisation, fact }: { organisation: RorOrganisation; fact: ProjectFact }) {
  const recorded = fact.fact_crossref_funder_id;
  const disagrees =
    Boolean(recorded) &&
    !organisation.crossref_funder_ids.some((id) => bareFunderId(id) === bareFunderId(recorded ?? ""));
  return (
    <>
      <h4>{displayName(organisation)}</h4>
      <dl className="funder-record">
        <dt>Names</dt>
        <dd>
          <Names organisation={organisation} />
        </dd>
        <dt>Status</dt>
        <dd>{organisation.status}</dd>
        {organisation.types.length > 0 && (
          <>
            <dt>Types</dt>
            <dd>{organisation.types.join(", ")}</dd>
          </>
        )}
        {organisation.country_codes.length > 0 && (
          <>
            <dt>Country</dt>
            <dd>{organisation.country_codes.join(", ")}</dd>
          </>
        )}
        <dt>ROR record</dt>
        <dd>
          <a href={organisation.links.ror}>{organisation.ror_id}</a>
        </dd>
        <dt>Crossref Funder ID</dt>
        <dd>
          {organisation.links.crossref_funders.length === 0 ? (
            "ROR holds none for this organisation."
          ) : (
            <ul>
              {organisation.links.crossref_funders.map((link, index) => (
                <li key={link}>
                  <a href={link}>{organisation.crossref_funder_ids[index]}</a>
                  {organisation.crossref_funder_ids[index] === organisation.crossref_funder_preferred && (
                    <span className="hint"> (preferred)</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </dd>
        {organisation.parents.length > 0 && (
          <>
            <dt>Parent organisations</dt>
            <dd>
              <ul>
                {organisation.parents.map((parent) => (
                  <li key={parent}>
                    <a href={parent}>{parent}</a>
                  </li>
                ))}
              </ul>
            </dd>
          </>
        )}
      </dl>
      {disagrees && (
        <p role="note" className="callout status-warn">
          The Crossref Funder ID recorded for this funder ({recorded}) is not one ROR holds for this
          organisation.
        </p>
      )}
      <p className="hint">Read from the pinned ROR dump {organisation.snapshot_ref}.</p>
    </>
  );
}

type Read = PanelLoad<RorOrganisation> | { state: "missing" };

function OrganisationSection({ rorId, fact }: { rorId: string | undefined; fact: ProjectFact }) {
  const api = useFundersApi();
  const [load, setLoad] = useState<Read>({ state: "loading" });
  useEffect(() => {
    if (!rorId) return undefined;
    const controller = new AbortController();
    api.organisation(rorId, controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setLoad(error instanceof OrganisationNotFound ? { state: "missing" } : { state: "failed", message: message(error) });
      },
    );
    return () => controller.abort();
  }, [api, rorId]);

  if (!rorId) {
    return <p>No ROR identifier is recorded for this funder, so there is no organisation record to show.</p>;
  }
  if (load.state === "loading") return <p>Reading the organisation's record…</p>;
  if (load.state === "missing") {
    return (
      <div role="alert" className="callout status-warn">
        <p>The pinned ROR dump holds no organisation at {rorId}. Check the identifier recorded for this funder.</p>
      </div>
    );
  }
  if (load.state === "failed") {
    return (
      <div role="alert" className="callout status-danger">
        <p>Data Director could not read the organisation's record: {load.message}</p>
      </div>
    );
  }
  return <Organisation organisation={load.value} fact={fact} />;
}

export function FunderViewer({
  projectId,
  subject,
  facts,
}: {
  projectId: string;
  subject: string;
  facts: ProjectFacts;
}) {
  const { decided, proposed } = funderFacts(facts, subject);
  const fact = decided[0] ?? proposed[0]?.fact;
  const rorId = fact?.fact_funder_ror?.trim() || undefined;
  return (
    <section className="funder" aria-labelledby={HEADING_ID}>
      <p>
        <Link to={factsPath(projectId)}>
          <ArrowLeft aria-hidden="true" size={16} /> Back to the project's facts
        </Link>
      </p>
      <h3 id={HEADING_ID}>Funder: {fact?.fact_funder_name ?? subject}</h3>
      {!fact && <p>This project holds no funder fact for {subject}: someone may have removed it.</p>}
      {decided.map((f) => (
        <p key={factKey(f)}>
          <strong>Decided:</strong> {describeFact(f)}
        </p>
      ))}
      {proposed.map((p) => (
        <p key={p.proposal}>
          <strong>Proposed by {p.agent_id}, waiting for a decision:</strong> {describeFact(p.fact)}
        </p>
      ))}
      {fact && <OrganisationSection key={rorId ?? ""} rorId={rorId} fact={fact} />}
    </section>
  );
}
