/**
 * The facts a project's researchers kept from their public ORCID records (docs/specs/projects.md):
 * what agents in the project are given to draft creators, affiliations, subjects and funding,
 * rather than ask for them.
 *
 * A person brings in their own record and ticks what to keep; nothing is ticked until they tick
 * it, and nothing is kept until they press Keep. The shell sends only what was ticked, by section
 * and ORCID put-code; the server reads the record from ORCID again and keeps ORCID's own words.
 * Keeping again replaces what they kept before, and Withdraw stops agents being given it.
 * Agents that call a hosted model are given these facts only where the deployment allows it.
 */

import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";

import { useProjectApi } from "../../project/api";
import { RECORD_ITEMS, RECORD_SECTIONS, type ResearcherRecord } from "../../project/researcher";
import { useSessionApi } from "../../session/api";
import { OrcidIcon } from "../ui/BrandIcon";
import { Button } from "../ui/Button";
import { formatDateTime } from "../../format";
import { ResearcherChooser } from "./ResearcherChooser";
import { ITEM_LABELS, SECTION_LABELS, choiceOf, itemsOf, sectionText } from "./researcherFacts";

const HEADING_ID = "researchers-heading";

type Load<T> =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: T };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function KeptRecord({
  record,
  mine,
  busy,
  onWithdraw,
}: {
  record: ResearcherRecord;
  mine: boolean;
  busy: boolean;
  onWithdraw: () => void;
}) {
  const sections = RECORD_SECTIONS.filter((s) => sectionText(record, s) !== "");
  return (
    <article className="researcher-record">
      <h3>
        {record.researcher_name ?? record.orcid_id} {mine && <span className="muted">(you)</span>}
      </h3>
      <p>
        <a href={record.orcid_id} target="_blank" rel="noreferrer">
          <OrcidIcon className="brand-icon" /> {record.orcid_id}
          <ExternalLink size="0.875em" aria-hidden="true" />
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </p>
      <dl className="researcher-facts">
        {sections.map((section) => (
          <div key={section}>
            <dt>{SECTION_LABELS[section]}</dt>
            <dd>{sectionText(record, section)}</dd>
          </div>
        ))}
        {RECORD_ITEMS.map((section) => {
          const items = itemsOf(record, section);
          if (items.length === 0) return null;
          return (
            <div key={section}>
              <dt>{ITEM_LABELS[section]}</dt>
              <dd>
                <ul className="plain-list">
                  {items.map(([code, text]) => (
                    <li key={code}>{text}</li>
                  ))}
                </ul>
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="hint">
        Read from ORCID on{" "}
        <time dateTime={record.record_retrieved_at}>
          {formatDateTime(record.record_retrieved_at)}
        </time>
        .
      </p>
      {mine && (
        <p>
          <Button variant="quiet" size="small" isPending={busy} onPress={onWithdraw}>
            Withdraw what you kept
          </Button>
        </p>
      )}
    </article>
  );
}

export function ResearcherPanel({ projectId }: { projectId: string }) {
  const api = useProjectApi();
  const sessions = useSessionApi();
  const [kept, setKept] = useState<Load<ResearcherRecord[]>>({ state: "loading" });
  const [me, setMe] = useState<string | null>(null);
  const [offered, setOffered] = useState<Load<ResearcherRecord> | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.researchers(projectId, controller.signal).then(
      (value) => setKept({ state: "loaded", value }),
      (error: unknown) => {
        if (!controller.signal.aborted) setKept({ state: "failed", message: message(error) });
      },
    );
    sessions.get(controller.signal).then(
      (session) => setMe(session.principal?.principalId ?? null),
      () => undefined,
    );
    return () => controller.abort();
  }, [api, sessions, projectId]);

  const mine = kept.state === "loaded" ? kept.value.find((r) => r.orcid_id === me) : undefined;

  const bringIn = () => {
    setSaid(null);
    setOffered({ state: "loading" });
    api.orcidRecord().then(
      (value) => setOffered({ state: "loaded", value }),
      (error: unknown) => setOffered({ state: "failed", message: message(error) }),
    );
  };

  const change = (action: Promise<ResearcherRecord[]>, done: string) => {
    setBusy(true);
    action.then(
      (value) => {
        setKept({ state: "loaded", value });
        setOffered(null);
        setSaid({ text: done, ok: true });
        setBusy(false);
      },
      (error: unknown) => {
        setSaid({ text: `Data Director could not do that: ${message(error)}`, ok: false });
        setBusy(false);
      },
    );
  };

  const records = () => {
    if (kept.state === "loading") return <p>Reading what the project holds…</p>;
    if (kept.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the researcher facts: {kept.message}</p>
        </div>
      );
    }
    if (kept.value.length === 0) {
      return <p>No researcher has kept any facts from ORCID in this project.</p>;
    }
    return kept.value.map((record) => (
      <KeptRecord
        key={record.orcid_id}
        record={record}
        mine={record.orcid_id === me}
        busy={busy}
        onWithdraw={() =>
          change(api.withdrawResearcher(projectId), "Agents in this project are no longer given what you kept.")
        }
      />
    ));
  };

  const chooser = () => {
    if (offered === null) {
      return (
        <p>
          <Button onPress={bringIn}>
            <OrcidIcon className="brand-icon" />{" "}
            {mine
              ? "Change what you keep from your ORCID record"
              : "Bring in facts from your ORCID record"}
          </Button>
        </p>
      );
    }
    if (offered.state === "loading") return <p>Reading your public ORCID record…</p>;
    if (offered.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read your ORCID record: {offered.message}</p>
        </div>
      );
    }
    return (
      <ResearcherChooser
        offered={offered.value}
        initial={choiceOf(mine)}
        busy={busy}
        onCancel={() => setOffered(null)}
        onKeep={(choice) =>
          change(api.keepResearcher(projectId, choice), "Kept. Agents in this project are given what you ticked.")
        }
      />
    );
  };

  return (
    <section className="researchers" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Researchers</h2>
      <p className="hint">
        Facts you keep here from your public ORCID record, such as your affiliation, keywords,
        works and funding, are given to the agents working on this project, so that they can fill
        in creators, subjects and funding instead of asking you. Agents that send data to a model
        hosted elsewhere are given them only where this deployment allows it. Your email address is
        never read.
      </p>
      <div role="status" className={said ? `callout ${said.ok ? "status-ok" : "status-danger"}` : undefined}>
        {said && <p>{said.text}</p>}
      </div>
      {records()}
      {chooser()}
    </section>
  );
}
