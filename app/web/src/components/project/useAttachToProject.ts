/**
 * Attaching a supporting document straight to a project, outside a turn (docs/specs/projects.md):
 * a file chosen is read as it is for a message (`readDocument`, or `readSource` for a Word
 * document or PDF, which the server reads inside the deployment) and held for the check
 * (`DocumentReviewDialog`). Only when the researcher confirms is it kept
 * (`POST /api/projects/{id}/documentation`); until then nothing is stored. What happened is said
 * through the page's announcer; a refusal is held for the caller to show beside its button, since
 * the page behind an open dialog is hidden from a screen reader. Used by the project's Documents
 * page and by the intake card.
 */

import { useState } from "react";

import {
  type AttachedDocument,
  type DocumentationSummary,
  isDocumentName,
  NotADocument,
  readDocument,
  readSource,
  sourceMediaType,
} from "../../conversation/documentation";
import { useProjectApi } from "../../project/api";
import { errorMessage } from "../../run/api";
import { useAnnounce } from "../ui/Announcer";

const NOT_A_DOCUMENT =
  "is not a document Data Director keeps. Attach a plain text (.txt), Markdown (.md), Word " +
  "(.docx) or PDF (.pdf) file. To add an inventory, use Add an inventory.";

export interface AttachToProject {
  /** The document read and awaiting the researcher's check, if any. */
  pending: AttachedDocument | null;
  saving: boolean;
  /** Why the last document chosen was not read or kept. */
  refused: string | null;
  choose(file: File | undefined): Promise<void>;
  save(checked: AttachedDocument): Promise<void>;
  discard(): void;
}

/** `kept` is told what the project holds, and the document kept, once it has been kept. */
export function useAttachToProject(
  projectId: string,
  kept?: (held: DocumentationSummary[], attached: DocumentationSummary | undefined) => void,
): AttachToProject {
  const api = useProjectApi();
  const announce = useAnnounce();
  const [pending, setPending] = useState<AttachedDocument | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

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
      const held = await api.attachDocument(projectId, checked);
      kept?.(held, held.findLast((d) => d.documentation_name === checked.name));
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

  function discard() {
    if (!saving) setPending(null);
  }

  return { pending, saving, refused, choose, save, discard };
}
