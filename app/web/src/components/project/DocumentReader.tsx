/**
 * One document in the project's reader: its name and state, who drafted it, and its text in three
 * tabs (a preview read by its media type, the stored text exactly, and its versions), then the
 * form to decide on it while its latest version is undecided.
 *
 * The preview is for reading. A decision names the stored text by its digest, which is what the
 * Source tab shows and what the deposit package will hold. While the person edits, the preview
 * shows their version, so that they can see it laid out before they approve it.
 *
 * An earlier version opens read-only, with a line saying it is not the latest and a link to the
 * latest. After a decision, focus moves to the document's heading, since the form it was in has
 * gone. A decision the server refused because the document has moved on is said in an alert,
 * which takes the focus, above the latest version, which the page has read again.
 */

import { Copy, Download } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";

import type {
  DocumentVersion,
  ProjectDocument,
  ProjectDocuments,
  ReviewRules,
} from "../../project/api";
import { dataUrl, fileName } from "../../project/media";
import { documentName } from "../../project/name";
import { Link } from "../../route";
import { Button } from "../ui/Button";
import { DecisionForm } from "./DecisionForm";
import { Provenance, State } from "./DocumentFacts";
import { DocumentHistory } from "./DocumentHistory";
import { DocumentPreview } from "./DocumentPreview";

export function DocumentReader({
  projectId,
  document,
  shown: wanted,
  rules,
  hrefFor,
  onDecided,
  onStale,
}: {
  projectId: string;
  document: ProjectDocument;
  /** The version asked for in the address, or null for the latest. */
  shown: number | null;
  rules: ReviewRules;
  /** The address of a version of this document; with no version, its latest. */
  hrefFor: (version?: DocumentVersion) => string;
  onDecided: (value: ProjectDocuments, said: string) => void;
  /** Reads the project again; answers why it could not, or null once it has. */
  onStale: () => Promise<string | null>;
}) {
  const latest = document.versions[document.versions.length - 1];
  const version = document.versions.find((v) => v.version === wanted) ?? latest;
  const name = documentName(document);
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const alert = useRef<HTMLDivElement>(null);
  const [stale, setStale] = useState<{
    detail: string;
    unread: string | null;
  } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const onEditing = useCallback((text: string | null) => setEditing(text), []);

  useEffect(() => {
    if (stale) alert.current?.focus();
  }, [stale]);

  if (!latest || !version) return null;
  const isLatest = version.version === latest.version;
  const earlier = document.versions.length - 1;

  const decided = (value: ProjectDocuments, said: string) => {
    setStale(null);
    onDecided(value, said);
    heading.current?.focus();
  };

  const refused = async (detail: string) => {
    const unread = await onStale();
    setStale({ detail, unread });
  };

  async function copy() {
    try {
      await navigator.clipboard.writeText(version?.text ?? "");
      setCopied("Copied the text.");
    } catch {
      setCopied("Could not copy; download the file instead.");
    }
  }

  const download = fileName(name, version.media_type);

  return (
    <article className="document-reader" aria-labelledby={headingId}>
      <header className="document-reader-head">
        <h2 id={headingId} ref={heading} tabIndex={-1}>
          {name}
        </h2>
        <p>
          Version {version.version}: <State version={version} />
        </p>
        <p className="hint">
          <Provenance version={version} />. <code>{version.media_type}</code>
          {version.conforms_to && (
            <>
              , following <code>{version.conforms_to}</code>
            </>
          )}
          .
        </p>
        {version.decision?.reason && (
          <p>
            <strong>Reason:</strong> {version.decision.reason}
          </p>
        )}
      </header>
      {!isLatest && (
        <div className="callout status-warn">
          <p>
            This is version {version.version}, kept as it was. The latest is version{" "}
            {latest.version}. <Link to={hrefFor()}>Read the latest version</Link>
          </p>
        </div>
      )}
      {stale && (
        <div role="alert" className="callout status-warn" ref={alert} tabIndex={-1}>
          {stale.unread === null ? (
            <p>
              Your decision was not recorded: {stale.detail} The latest version is shown below. Read
              it, then decide again.
            </p>
          ) : (
            <p>
              Your decision was not recorded: {stale.detail} Data Director could not read the latest
              version: {stale.unread} Reload the page before you decide again.
            </p>
          )}
        </div>
      )}
      <Tabs className="document-tabs">
        <div className="document-tabs-bar">
          <TabList aria-label={`${name}, version ${version.version}`} className="document-tab-list">
            <Tab id="preview" className="document-tab">
              Preview
            </Tab>
            <Tab id="source" className="document-tab">
              Source
            </Tab>
            {earlier > 0 && (
              <Tab id="history" className="document-tab">
                Versions ({document.versions.length})
              </Tab>
            )}
          </TabList>
          <p className="document-actions">
            <Button variant="quiet" size="small" icon={Copy} onPress={() => void copy()}>
              Copy the text
            </Button>{" "}
            <a
              className="button button-quiet button-small"
              href={dataUrl(version.media_type, version.text)}
              download={download}
            >
              <Download className="button-icon" size="1.125em" aria-hidden="true" />
              Download {download}
            </a>{" "}
            <span role="status">{copied}</span>
          </p>
        </div>
        <TabPanel id="preview" className="document-tab-panel">
          {editing !== null && (
            <p className="callout status-warn">
              The preview shows your edited version. It is not saved until you approve it.
            </p>
          )}
          <DocumentPreview
            text={editing ?? version.text}
            mediaType={version.media_type}
            name={name}
          />
        </TabPanel>
        <TabPanel id="source" className="document-tab-panel">
          <p className="hint">
            The text exactly as it is stored. A decision is on this text, and it is what goes into
            the deposit package.
          </p>
          <pre className="json-view document-text">{version.text}</pre>
        </TabPanel>
        {earlier > 0 && (
          <TabPanel id="history" className="document-tab-panel">
            <DocumentHistory document={document} shown={version.version} hrefFor={hrefFor} />
          </TabPanel>
        )}
      </Tabs>
      {isLatest && version.state === "proposed" && (
        <DecisionForm
          key={`${version.document_id}:${version.version}`}
          projectId={projectId}
          name={name}
          version={version}
          rules={rules}
          onDecided={decided}
          onStale={refused}
          onEditing={onEditing}
        />
      )}
    </article>
  );
}
