/**
 * The sources page (`/sources`): the external sources Data Director reads, the licence each is
 * under and the credit each asks for, from `GET /api/sources`. The code is MIT; the data is the
 * sources', under their own licences, and a source's terms bind anyone who reuses what it supplied.
 */

import "./SourcesPage.css";

import { useEffect } from "react";

import { type SourceCredit, fetchSources } from "../../sources/credits";
import { useResource } from "../../useResource";
import { PageHeader } from "../frame/PageHeader";

const GROUPS: readonly { kind: SourceCredit["kind"]; title: string }[] = [
  { kind: "data", title: "Data" },
  { kind: "service", title: "Services read at run time" },
  { kind: "font", title: "Fonts" },
];

const USE: Record<SourceCredit["use"], string> = {
  pinned: "A copy kept with its licence",
  live: "Asked at run time; nothing kept",
  both: "A copy kept, and asked at run time",
};

function Source({ source }: { source: SourceCredit }) {
  return (
    <li id={`source-${source.id}`} className="source-credit">
      <h3>
        <a href={source.url} target="_blank" rel="noreferrer">
          {source.name}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </h3>
      <p>{source.attribution}</p>
      {source.badge_url && (
        <p>
          <img src={source.badge_url} alt={`${source.name} attribution badge`} height={32} />
        </p>
      )}
      <p className="muted">
        Licence:{" "}
        <a href={source.licence_url} target="_blank" rel="noreferrer">
          <code>{source.licence}</code>
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
        {" · "}
        {USE[source.use]}
        {source.terms_url && (
          <>
            {" · "}
            <a href={source.terms_url} target="_blank" rel="noreferrer">
              Terms
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          </>
        )}
      </p>
      {source.non_commercial && (
        <p>
          <span className="status status-warn">Non-commercial terms</span> This source&rsquo;s own
          terms limit use to non-commercial purposes.
        </p>
      )}
      {source.citation && <p className="muted">Cite as: {source.citation}</p>}
    </li>
  );
}

export function SourcesPage({ load = fetchSources }: { load?: typeof fetchSources }) {
  const { resource: state } = useResource("sources", (_, signal) => load(signal));

  useEffect(() => {
    if (state.state !== "loaded" || !window.location.hash) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView?.();
  }, [state.state]);

  return (
    <>
      <PageHeader title="Sources and licences">
        <p className="hint">
          Data Director&rsquo;s code is under the MIT licence. The data and services below belong to
          their publishers and stay under their own licences and terms; each is credited as its
          publisher asks. The licence of a source applies to what it supplied, wherever that appears
          in a result.
        </p>
      </PageHeader>
      {state.state === "loading" && <p role="status">Loading…</p>}
      {state.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its sources: {state.message}.</p>
        </div>
      )}
      {state.state === "loaded" &&
        GROUPS.map(({ kind, title }) => {
          const group = state.value.filter((source) => source.kind === kind);
          return (
            group.length > 0 && (
              <section key={kind} aria-labelledby={`sources-${kind}`}>
                <h2 id={`sources-${kind}`}>{title}</h2>
                <ul className="source-credits">
                  {group.map((source) => (
                    <Source key={source.id} source={source} />
                  ))}
                </ul>
              </section>
            )
          );
        })}
    </>
  );
}
