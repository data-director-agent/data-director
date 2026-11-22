/**
 * Attaching a supporting document to a project from outside a conversation (docs/specs/projects.md):
 * the project's Documents page offers **Attach a document**, beside **Add an inventory**, and lists
 * the documents the project holds beside those agents drafted (`DocumentList`). A file chosen is read and checked as one attached to a
 * message (`DocumentReviewDialog`: its text, who reads it and what the personal-data check found, #473),
 * and kept only when the researcher confirms (`useAttachToProject`); the page is told (`onAttached`),
 * so that it lists the document and opens it. A refusal closes the check and is shown beside the
 * button; the document can be chosen again. The intake card offers the same button
 * (`AttachDocumentButton`).
 *
 * Where the profile refuses attached documents the page does not offer it
 * (`AttachDocumentOffer`); the server refuses it too, so this holds no policy.
 */

import { Paperclip } from "lucide-react";
import { useMemo } from "react";
import { FileTrigger } from "react-aria-components";

import {
  type DocumentationSummary,
  type DocumentReaders,
  DOCUMENT_EXTENSIONS,
  DOCUMENT_MEDIA_TYPES,
  documentReaders,
} from "../../conversation/documentation";
import type { Directory } from "../../manifest/normalise";
import { DocumentReviewDialog } from "../conversation/DocumentReviewDialog";
import { Button } from "../ui/Button";
import { type AttachToProject, useAttachToProject } from "./useAttachToProject";

/** `AttachDocument`, where the agents and profile are known and the profile allows documents. */
/** Called with the documents the project holds once one is attached, and the one attached. */
export type OnAttached = (held: DocumentationSummary[], attached: DocumentationSummary | undefined) => void;

export function AttachDocumentOffer({
  projectId,
  directory,
  onAttached,
}: {
  projectId: string;
  directory: Directory | null | undefined;
  onAttached: OnAttached;
}) {
  const readers = useMemo(
    () => directory && documentReaders(directory.agents, directory.orchestratorId),
    [directory],
  );
  if (!readers || !directory?.documentsAllowed) return null;
  return (
    <p className="project-document-actions">
      <AttachDocument projectId={projectId} readers={readers} onAttached={onAttached} />
    </p>
  );
}

export function AttachDocument({
  projectId,
  readers,
  onAttached,
}: {
  projectId: string;
  /** Who reads an attached document's text, for the check to say (`documentReaders`). */
  readers: DocumentReaders;
  onAttached: OnAttached;
}) {
  const attach = useAttachToProject(projectId, onAttached);

  return <AttachDocumentButton attach={attach} readers={readers} label="Attach a document" />;
}

/** The button that chooses a document to attach to the project, why the last was refused, and
 * the check it opens (`useAttachToProject`). */
export function AttachDocumentButton({
  attach,
  readers,
  label,
}: {
  attach: AttachToProject;
  readers: DocumentReaders;
  label: string;
}) {
  return (
    <>
      <span className="attach-document">
        <FileTrigger
          acceptedFileTypes={[...DOCUMENT_MEDIA_TYPES, ...DOCUMENT_EXTENSIONS]}
          onSelect={(files) => void attach.choose(files?.[0])}
        >
          <Button icon={Paperclip} isPending={attach.saving}>
            {label}
          </Button>
        </FileTrigger>
      </span>
      {attach.refused && <span role="alert">{attach.refused}</span>}
      <DocumentReviewDialog
        pending={attach.pending}
        readers={readers}
        onAttach={(checked) => void attach.save(checked)}
        onDiscard={attach.discard}
      />
    </>
  );
}
