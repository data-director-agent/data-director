/**
 * The project's documents, grouped by the state of each one's latest version, those waiting for
 * a decision first, then the researcher facts kept from ORCID, the repository chosen, the statement of how generative AI was used and
 * the deposit package. Each entry is a link, so it can be opened in a new tab and left with Back;
 * the open one is marked as the current page.
 */

import {
  BookOpen,
  Braces,
  ClipboardList,
  FileText,
  Landmark,
  type LucideIcon,
  Package,
  Sparkles,
  Table,
  UserRound,
} from "lucide-react";

import type { ProjectDocument, VersionState } from "../../project/api";
import { documentName } from "../../project/name";
import { Link } from "../../route";

const ICONS: Record<string, LucideIcon> = {
  readme: BookOpen,
  data_dictionary: Table,
  metadata_record: Braces,
  dmp: ClipboardList,
};

const GROUPS: { state: VersionState; heading: string }[] = [
  { state: "proposed", heading: "To review" },
  { state: "approved", heading: "Approved" },
  { state: "rejected", heading: "Rejected" },
];

export const DISCLOSURE = "disclosure";
export const REPOSITORY = "repository";
export const DEPOSIT = "deposit";
export const RESEARCHERS = "researchers";
/** The entries that are not documents, each opening a panel of its own. */
export const PANELS: readonly string[] = [RESEARCHERS, REPOSITORY, DISCLOSURE, DEPOSIT];

/** The state of a document's latest version. */
export function stateOf(document: ProjectDocument): VersionState | undefined {
  return document.versions[document.versions.length - 1]?.state;
}

function Entry({
  to,
  icon: Icon,
  label,
  detail,
  current,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
  detail?: string;
  current: boolean;
}) {
  return (
    <li>
      <Link
        to={to}
        className="document-entry"
        {...(current ? { "aria-current": "page" as const } : {})}
      >
        <Icon className="document-entry-icon" size="1.125em" aria-hidden="true" />
        <span className="document-entry-name">{label}</span>
        {detail && <span className="document-entry-detail">{detail}</span>}
      </Link>
    </li>
  );
}

export function DocumentList({
  documents,
  selected,
  hrefFor,
}: {
  documents: ProjectDocument[];
  /** The open document's id, or one of `PANELS`. */
  selected: string | null;
  hrefFor: (id: string) => string;
}) {
  return (
    <nav className="document-list" aria-label="Documents">
      {GROUPS.map(({ state, heading }) => {
        const group = documents.filter((document) => stateOf(document) === state);
        if (group.length === 0) return null;
        return (
          <section key={state} className={`document-group document-group-${state}`}>
            <h2 className="document-group-heading">
              {heading} <span className="document-group-count">({group.length})</span>
            </h2>
            <ul className="plain-list">
              {group.map((document) => (
                <Entry
                  key={document.document_id}
                  to={hrefFor(document.document_id)}
                  icon={ICONS[document.document_kind] ?? FileText}
                  label={documentName(document)}
                  detail={`version ${document.versions[document.versions.length - 1]?.version ?? 1}`}
                  current={selected === document.document_id}
                />
              ))}
            </ul>
          </section>
        );
      })}
      <section className="document-group">
        <h2 className="document-group-heading">About the documents</h2>
        <ul className="plain-list">
          <Entry
            to={hrefFor(RESEARCHERS)}
            icon={UserRound}
            label="Researchers"
            current={selected === RESEARCHERS}
          />
          <Entry
            to={hrefFor(REPOSITORY)}
            icon={Landmark}
            label="Repository"
            current={selected === REPOSITORY}
          />
          <Entry
            to={hrefFor(DISCLOSURE)}
            icon={Sparkles}
            label="Use of generative AI"
            current={selected === DISCLOSURE}
          />
          <Entry
            to={hrefFor(DEPOSIT)}
            icon={Package}
            label="Deposit package"
            current={selected === DEPOSIT}
          />
        </ul>
      </section>
    </nav>
  );
}
