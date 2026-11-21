/**
 * What the message box offers for attaching: the chip of what is attached and the button to attach
 * a file. Making an inventory is not offered here; the
 * project's panel and page offer it (AddInventory.tsx). An inventory and a document
 * may each be attached once (docs/specs/app.md); a document only where the profile allows it
 * (`documents`, docs/specs/projects.md). The picker passes on every file chosen, so that those
 * not attached can be named (#1170).
 */

import { Paperclip } from "lucide-react";
import { FileTrigger } from "react-aria-components";

import {
  type AttachedDocument,
  DOCUMENT_EXTENSIONS,
  DOCUMENT_MEDIA_TYPES,
} from "../../conversation/documentation";
import type { AttachedInventory } from "../../conversation/inventory";
import { Button } from "../ui/Button";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";

export function ComposerAttach({
  attached,
  attachedDocument,
  documents,
  busy,
  onAttachFiles,
  onRemoveInventory,
  onRemoveDocument,
}: {
  attached: AttachedInventory | null;
  attachedDocument: AttachedDocument | null;
  documents: boolean;
  busy: boolean;
  onAttachFiles: (files: FileList | null) => void;
  onRemoveInventory: () => void;
  onRemoveDocument: () => void;
}) {
  return (
    <>
      <div className="composer-attach">
        {attached && (
          <InventoryChip
            fileCount={attached.fileCount}
            madeAt={attached.madeAt}
            name={attached.name}
            source={{ document: attached.document }}
            onRemove={onRemoveInventory}
          />
        )}
        {attachedDocument && (
          <DocumentChip
            name={attachedDocument.name}
            size={attachedDocument.size}
            onRemove={onRemoveDocument}
          />
        )}
        {!(attached && attachedDocument) && (
          <FileTrigger
            acceptedFileTypes={[
              "application/json",
              ".json",
              ...(documents ? [...DOCUMENT_MEDIA_TYPES, ...DOCUMENT_EXTENSIONS] : []),
            ]}
            onSelect={onAttachFiles}
          >
            <Button icon={Paperclip} isDisabled={busy}>
              Attach a file
            </Button>
          </FileTrigger>
        )}
      </div>
    </>
  );
}
