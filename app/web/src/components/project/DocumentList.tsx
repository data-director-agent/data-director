/**
 * The project's documents, grouped by the state of each one's latest version, those waiting for
 * a decision first, then the documents a researcher attached (**Attached documents**), each with
 * what kind of file it came as, its size and when it was attached. Each entry is a link, so it can be opened in a new tab and left with Back; the
 * open one is marked as the current page. What is about the project rather than one document (the
 * researchers, its facts, the repository, the use of generative AI and the deposit package) has a
 * tab of its own (`ProjectNav`).
 */

import {
  BookOpen,
  Braces,
  ClipboardList,
  File,
  FileCode,
  FileText,
  FileType,
  type LucideIcon,
  Table,
} from "lucide-react";

import type { DocumentationSummary } from "../../conversation/documentation";
import type { ProjectDocument, VersionState } from "../../project/api";
import {
  type AttachedKind,
  attachedDetail,
  attachedKind,
} from "../../project/attached";
import { documentName } from "../../project/name";
import { Link } from "../../route";
import type { PanelTab } from "./ProjectPanelPage";

const ICONS: Record<string, LucideIcon> = {
  readme: BookOpen,
  data_dictionary: Table,
  metadata_record: Braces,
  dmp: ClipboardList,
};

const ATTACHED_ICONS: Record<AttachedKind, LucideIcon> = {
  word: FileType,
  pdf: File,
  markdown: FileCode,
  text: FileText,
};

const GROUPS: { state: VersionState; heading: string }[] = [
  { state: "proposed", heading: "To review" },
  { state: "approved", heading: "Approved" },
  { state: "rejected", heading: "Rejected" },
];

/** The entries that were once listed here and are now tabs, by their old `?doc=` id, so that an
 * old link still lands on them. */
export const FORMER_PANELS: Readonly<Record<string, PanelTab>> = {
  researchers: "people",
  facts: "facts",
  repository: "repository",
  disclosure: "ai-use",
  deposit: "deposit",
};

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
        <Icon
          className="document-entry-icon"
          size="1.125em"
          aria-hidden="true"
        />
        <span className="document-entry-name">{label}</span>
        {detail && <span className="document-entry-detail">{detail}</span>}
      </Link>
    </li>
  );
}

function Attached({
  attached,
  selected,
  hrefFor,
}: {
  attached: readonly DocumentationSummary[];
  selected: string | null;
  hrefFor: (digest: string) => string;
}) {
  if (attached.length === 0) return null;
  return (
    <section className="document-group document-group-attached">
      <h2 className="document-group-heading">
        Attached documents{" "}
        <span className="document-group-count">({attached.length})</span>
      </h2>
      <ul className="plain-list">
        {attached.map((document) => (
          <Entry
            key={document.documentation_digest}
            to={hrefFor(document.documentation_digest)}
            icon={ATTACHED_ICONS[attachedKind(document)]}
            label={document.documentation_name}
            detail={`${attachedDetail(document)}${document.documentation_is_plan ? " · Data Management Plan" : ""}`}
            current={selected === document.documentation_digest}
          />
        ))}
      </ul>
    </section>
  );
}

export function DocumentList({
  documents,
  attached,
  selected,
  selectedAttached,
  hrefFor,
  attachedHrefFor,
}: {
  documents: ProjectDocument[];
  /** The documents a researcher attached to the project. */
  attached: readonly DocumentationSummary[];
  /** The open document's id. */
  selected: string | null;
  /** The open attached document's digest. */
  selectedAttached: string | null;
  hrefFor: (id: string) => string;
  attachedHrefFor: (digest: string) => string;
}) {
  return (
    <nav className="document-list" aria-label="Documents">
      {GROUPS.map(({ state, heading }) => {
        const group = documents.filter(
          (document) => stateOf(document) === state,
        );
        if (group.length === 0) return null;
        return (
          <section
            key={state}
            className={`document-group document-group-${state}`}
          >
            <h2 className="document-group-heading">
              {heading}{" "}
              <span className="document-group-count">({group.length})</span>
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
      <Attached
        attached={attached}
        selected={selectedAttached}
        hrefFor={attachedHrefFor}
      />
    </nav>
  );
}
