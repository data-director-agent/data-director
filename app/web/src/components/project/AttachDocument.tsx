/**
 * Attaching a supporting document to a project from outside a conversation (docs/specs/projects.md):
 * the project's Documents page offers **Attach a document**, beside **Add an inventory**, and lists
 * the documents the project holds. A file chosen is read as it is for a message (`readDocument`,
 * or `readSource` for a Word document or PDF, which the server reads inside the deployment), then
 * opened in the same check as one attached to a message (`DocumentReviewDialog`: its text, who
 * reads it and what the personal-data check found, #473). Only when the researcher confirms is it
 * kept (`POST /api/projects/{id}/documentation`); until then nothing is stored. What happened is
 * said through the page's announcer. A refusal closes the check and is shown on the page, since
 * the page behind an open dialog is hidden from a screen reader; the document can be chosen again.
 *
 * Where the profile refuses attached documents the page does not offer it
 * (`AttachDocumentOffer`); the server refuses it too, so this holds no policy.
 */

import { Paperclip } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { FileTrigger } from "react-aria-components";

import {
  type AttachedDocument,
  type DocumentationSummary,
  type DocumentReaders,
  DOCUMENT_EXTENSIONS,
  DOCUMENT_MEDIA_TYPES,
  describeSize,
  documentReaders,
  isDocumentName,
  NotADocument,
  readDocument,
  readSource,
  sourceMediaType,
} from "../../conversation/documentation";
import type { Directory } from "../../manifest/normalise";
import { useProjectApi } from "../../project/api";
import { errorMessage } from "../../run/api";
import { DocumentReviewDialog } from "../conversation/DocumentReviewDialog";
import { useAnnounce } from "../ui/Announcer";
import { Button } from "../ui/Button";

const NOT_A_DOCUMENT =
  "is not a document Data Director keeps. Attach a plain text (.txt), Markdown (.md), Word " +
  "(.docx) or PDF (.pdf) file. To add an inventory, use Add an inventory.";

/** `AttachDocument`, where the agents and profile are known and the profile allows documents. */
export function AttachDocumentOffer({
  projectId,
  directory,
}: {
  projectId: string;
  directory: Directory | null | undefined;
}) {
  const readers = useMemo(
    () => directory && documentReaders(directory.agents, directory.orchestratorId),
    [directory],
  );
  if (!readers || !directory?.documentsAllowed) return null;
  return (
    <p className="project-document-actions">
      <AttachDocument projectId={projectId} readers={readers} />
    </p>
  );
}

export function AttachDocument({
  projectId,
  readers,
}: {
  projectId: string;
  /** Who reads an attached document's text, for the check to say (`documentReaders`). */
  readers: DocumentReaders;
}) {
  const api = useProjectApi();
  const [held, setHeld] = useState<DocumentationSummary[]>([]);
  const [pending, setPending] = useState<AttachedDocument | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const announce = useAnnounce();

  // The documents the project holds; if they cannot be read the button still works.
  useEffect(() => {
    const controller = new AbortController();
    api.documentation(projectId, controller.signal).then(setHeld, () => undefined);
    return () => controller.abort();
  }, [api, projectId]);

  async function choose(file: File | undefined) {
    if (!file) return;
    try {
      if (!isDocumentName(file.name)) throw new NotADocument(`${file.name} ${NOT_A_DOCUMENT}`);
      const source = sourceMediaType(file.name);
      setPending(
        source === null ? readDocument(await file.text(), file.name) : await readSource(file, source),
      );
      setRefused(null);
    } catch (e) {
      setRefused(
        e instanceof NotADocument
          ? e.message
          : `Data Director could not read ${file.name}: ${errorMessage(e)}`,
      );
    }
  }

  async function save(checked: AttachedDocument) {
    setSaving(true);
    try {
      setHeld(await api.attachDocument(projectId, checked));
      setPending(null);
      setRefused(null);
      announce(`${checked.name} attached to the project.`);
    } catch (e) {
      setPending(null);
      setRefused(`The document was not attached: ${errorMessage(e)} Choose it again to retry.`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <span className="attach-document">
        <FileTrigger
          acceptedFileTypes={[...DOCUMENT_MEDIA_TYPES, ...DOCUMENT_EXTENSIONS]}
          onSelect={(files) => void choose(files?.[0])}
        >
          <Button icon={Paperclip} isPending={saving}>
            Attach a document
          </Button>
        </FileTrigger>
      </span>
      {refused && <span role="alert">{refused}</span>}
      {held.length > 0 && (
        <section aria-label="Attached documents" className="attached-documents">
          <h2 className="attached-documents-heading">Attached documents</h2>
          <ul className="plain-list">
            {held.map((d) => (
              <li key={`${d.documentation_name}:${d.documentation_digest}`}>
                {d.documentation_name}{" "}
                <span className="hint">({describeSize(d.documentation_size)})</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <DocumentReviewDialog
        pending={pending}
        readers={readers}
        onAttach={(checked) => void save(checked)}
        onDiscard={() => {
          if (!saving) setPending(null);
        }}
      />
    </>
  );
}
