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
import { type FormEvent, useEffect, useState } from "react";

import {
  type KeepChoice,
  RECORD_ITEMS,
  RECORD_SECTIONS,
  type RecordItems,
  type RecordSection,
  type ResearcherRecord,
  useProjectApi,
} from "../../project/api";
import { useSessionApi } from "../../session/api";
import { OrcidIcon } from "../ui/BrandIcon";
import { Button } from "../ui/Button";

const HEADING_ID = "researchers-heading";

const SECTION_LABELS: Record<RecordSection, string> = {
  researcher_name: "Name",
  other_names: "Other names",
  biography: "Biography",
  keywords: "Keywords",
  country: "Country",
  researcher_links: "Web pages",
  external_identifiers: "Other identifiers",
};

const ITEM_LABELS: Record<RecordItems, string> = {
  affiliations: "Affiliations",
  works: "Works",
  fundings: "Funding",
};

type Load<T> =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: T };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function years(start?: number, end?: number): string {
  if (!start && !end) return "";
  return ` (${start ?? "?"}–${end ?? "present"})`;
}

/** What one section of a record says, in a line. */
function sectionText(record: ResearcherRecord, section: RecordSection): string {
  switch (section) {
    case "researcher_name":
    case "biography":
      return record[section] ?? "";
    case "other_names":
    case "keywords":
    case "country":
      return (record[section] ?? []).join(", ");
    case "researcher_links":
      return (record.researcher_links ?? []).map((l) => l.link_title ?? l.link_url).join(", ");
    case "external_identifiers":
      return (record.external_identifiers ?? [])
        .map((i) => `${i.identifier_type} ${i.identifier_value}`)
        .join(", ");
  }
}

/** Each item of an itemised section, by put-code, in a line. */
function itemsOf(record: ResearcherRecord, section: RecordItems): [string, string][] {
  if (section === "affiliations") {
    return (record.affiliations ?? []).map((a) => [
      a.put_code,
      `${a.role_title ? `${a.role_title}, ` : ""}${a.organisation_name}${years(a.start_year, a.end_year)}`,
    ]);
  }
  if (section === "works") {
    return (record.works ?? []).map((w) => [
      w.put_code,
      `${w.work_title}${w.publication_year ? ` (${w.publication_year})` : ""}`,
    ]);
  }
  return (record.fundings ?? []).map((f) => [
    f.put_code,
    `${f.funding_title}, ${f.funder_name}${years(f.start_year, f.end_year)}`,
  ]);
}

/** What `record` holds, as the choice that would keep it again. */
function choiceOf(record: ResearcherRecord | undefined): KeepChoice {
  return {
    sections: record ? RECORD_SECTIONS.filter((s) => sectionText(record, s) !== "") : [],
    affiliations: (record?.affiliations ?? []).map((a) => a.put_code),
    works: (record?.works ?? []).map((w) => w.put_code),
    fundings: (record?.fundings ?? []).map((f) => f.put_code),
  };
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
          {new Date(record.record_retrieved_at).toLocaleString()}
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

function Chooser({
  offered,
  initial,
  busy,
  onKeep,
  onCancel,
}: {
  offered: ResearcherRecord;
  initial: KeepChoice;
  busy: boolean;
  onKeep: (choice: KeepChoice) => void;
  onCancel: () => void;
}) {
  const [choice, setChoice] = useState<KeepChoice>(initial);
  const sections = RECORD_SECTIONS.filter((s) => sectionText(offered, s) !== "");

  const toggleSection = (section: RecordSection, on: boolean) =>
    setChoice((c) => ({
      ...c,
      sections: on ? [...c.sections, section] : c.sections.filter((s) => s !== section),
    }));
  const toggleItem = (section: RecordItems, code: string, on: boolean) =>
    setChoice((c) => ({
      ...c,
      [section]: on ? [...c[section], code] : c[section].filter((k) => k !== code),
    }));
  const setAll = (section: RecordItems, on: boolean) =>
    setChoice((c) => ({ ...c, [section]: on ? itemsOf(offered, section).map(([k]) => k) : [] }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onKeep(choice);
  };

  return (
    <form className="researcher-chooser" onSubmit={submit} aria-label="Choose what to keep">
      <p className="hint">
        Nothing is ticked until you tick it. Only what you tick is kept in this project and given
        to its agents.
      </p>
      {sections.length > 0 && (
        <fieldset className="field">
          <legend>About you</legend>
          {sections.map((section) => (
            <div className="field-check" key={section}>
              <input
                type="checkbox"
                id={`keep-${section}`}
                checked={choice.sections.includes(section)}
                onChange={(event) => toggleSection(section, event.target.checked)}
              />
              <label htmlFor={`keep-${section}`}>
                {`${SECTION_LABELS[section]}: ${sectionText(offered, section)}`}
              </label>
            </div>
          ))}
        </fieldset>
      )}
      {RECORD_ITEMS.map((section) => {
        const items = itemsOf(offered, section);
        if (items.length === 0) return null;
        const all = items.every(([code]) => choice[section].includes(code));
        return (
          <fieldset className="field" key={section}>
            <legend>{ITEM_LABELS[section]}</legend>
            <p>
              <Button variant="quiet" size="small" onPress={() => setAll(section, !all)}>
                {all ? "Untick all" : "Tick all"}
                <span className="visually-hidden"> {ITEM_LABELS[section].toLowerCase()}</span>
              </Button>
            </p>
            {items.map(([code, text]) => (
              <div className="field-check" key={code}>
                <input
                  type="checkbox"
                  id={`keep-${section}-${code}`}
                  checked={choice[section].includes(code)}
                  onChange={(event) => toggleItem(section, code, event.target.checked)}
                />
                <label htmlFor={`keep-${section}-${code}`}>{text}</label>
              </div>
            ))}
            {section === "works" && offered.works_omitted ? (
              <p className="hint">
                Your {offered.works_omitted} older works are not offered, to keep what agents are
                given short.
              </p>
            ) : null}
          </fieldset>
        );
      })}
      <p className="document-actions">
        <Button type="submit" variant="primary" isPending={busy}>
          Keep the ticked facts
        </Button>{" "}
        <Button variant="quiet" isDisabled={busy} onPress={onCancel}>
          Cancel
        </Button>
      </p>
    </form>
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
      <Chooser
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
