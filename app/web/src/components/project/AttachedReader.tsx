/**
 * One document a researcher attached to the project, in the Documents tab's reader
 * (docs/specs/projects.md, Documentation): its name, what kind of file it came as, its size and
 * when it was attached, then its text in two tabs. **Preview** lays out a copy to read (for a Word
 * document, its file read again as Markdown, so that headings, lists and tables show as they do
 * in the original); **Text** is the stored text exactly, which is what agents in the project read.
 * The original Word or PDF file can be downloaded, and the text copied. A person may mark it as the
 * project's Data Management Plan (`PlanMark`).
 *
 * An attached document is supporting material: nobody decides on it, so the reader has no
 * decision form. If its text cannot be read, it says so; the rest of the page is unaffected.
 */

import { Copy, Download, Paperclip } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";

import type { DocumentationSummary } from "../../conversation/documentation";
import { attachedKindLabel, attachedOn } from "../../project/attached";
import { useProjectApi } from "../../project/api";
import {
  type DocumentationText,
  documentationPath,
} from "../../project/documentation";
import { errorMessage } from "../../run/api";
import { homePath, Link } from "../../route";
import { Button } from "../ui/Button";
import { DocumentPreview } from "./DocumentPreview";
import { PlanMark } from "./PlanMark";

type Read =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; preview: DocumentationText; stored: DocumentationText };

export function AttachedReader({
  projectId,
  document,
  onChange,
}: {
  projectId: string;
  document: DocumentationSummary;
  /** The documents the project holds, as the server lists them after the plan is marked. */
  onChange: (held: DocumentationSummary[]) => void;
}) {
  const api = useProjectApi();
  const headingId = useId();
  const digest = document.documentation_digest;
  const [read, setRead] = useState<Read>({ state: "loading" });
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    Promise.all([
      api.documentationText(projectId, digest, true, signal),
      api.documentationText(projectId, digest, false, signal),
    ]).then(
      ([preview, stored]) => setRead({ state: "loaded", preview, stored }),
      (e: unknown) => {
        if (!signal.aborted)
          setRead({ state: "failed", message: errorMessage(e) });
      },
    );
    return () => controller.abort();
  }, [api, projectId, digest]);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied("Copied the text.");
    } catch {
      setCopied("Could not copy; select the text on the Text tab instead.");
    }
  }

  const name = document.documentation_name;
  const original = document.documentation_source_media_type;

  const body = () => {
    if (read.state === "loading") return <p role="status">Reading {name}…</p>;
    if (read.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>
            Data Director could not read {name}: {read.message}
          </p>
        </div>
      );
    }
    return (
      <Tabs className="document-tabs">
        <div className="document-tabs-bar">
          <TabList aria-label={name} className="document-tab-list">
            <Tab id="preview" className="document-tab">
              Preview
            </Tab>
            <Tab id="text" className="document-tab">
              Text
            </Tab>
          </TabList>
          <p className="document-actions">
            <Button
              variant="quiet"
              size="small"
              icon={Copy}
              onPress={() => void copy(read.stored.text)}
            >
              Copy the text
            </Button>{" "}
            <span role="status">{copied}</span>
          </p>
        </div>
        <TabPanel id="preview" className="document-tab-panel">
          <DocumentPreview
            text={read.preview.text}
            mediaType={read.preview.mediaType}
            name={name}
          />
        </TabPanel>
        <TabPanel id="text" className="document-tab-panel">
          <p className="hint">
            The text exactly as the project holds it. This is what agents in
            this project read.
          </p>
          <pre className="json-view document-text">{read.stored.text}</pre>
        </TabPanel>
      </Tabs>
    );
  };

  return (
    <article
      className="document-reader attached-reader"
      aria-labelledby={headingId}
    >
      <header className="document-reader-head">
        <h2 id={headingId}>{name}</h2>
        <p className="attached-reader-facts">
          <span className="status attached-badge">
            <Paperclip size="1em" aria-hidden="true" /> Attached document
          </span>{" "}
          <span className="hint">
            {attachedKindLabel(document)}, added{" "}
            <time dateTime={document.documentation_added_at}>
              {attachedOn(document)}
            </time>
          </span>
        </p>
        <p className="hint">
          Agents in this project read it as supporting material when they draft
          and check documents. Nobody needs to approve it. To work from it,{" "}
          <Link to={homePath({})}>start a conversation</Link>.
        </p>
        <PlanMark
          projectId={projectId}
          document={document}
          onChange={onChange}
        />
        {original && (
          <p>
            <a
              className="button button-quiet button-small"
              href={`${documentationPath(projectId, digest)}?original`}
              download={name}
            >
              <Download
                className="button-icon"
                size="1.125em"
                aria-hidden="true"
              />
              Download the original {attachedKindLabel(document)}
            </a>
          </p>
        )}
      </header>
      {body()}
    </article>
  );
}
