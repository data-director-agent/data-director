/**
 * What the message box offers for attaching: the chip of what is attached, the buttons to attach
 * a file or make an inventory, and the note on what may be attached. An inventory and a document
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
import { MakeInventoryDialog } from "../inventory/MakeInventoryDialog";
import { Button } from "../ui/Button";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";

export function ComposerAttach({
  attached,
  attachedDocument,
  documents,
  busy,
  onAttachFiles,
  onAttachMade,
  onRemoveInventory,
  onRemoveDocument,
}: {
  attached: AttachedInventory | null;
  attachedDocument: AttachedDocument | null;
  documents: boolean;
  busy: boolean;
  onAttachFiles: (files: FileList | null) => void;
  onAttachMade: (file: File) => void;
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
            <Button icon={Paperclip} isDisabled={busy} aria-describedby="attach-hint">
              Attach a file
            </Button>
          </FileTrigger>
        )}
        {!attached && <MakeInventoryDialog isDisabled={busy} onAttach={onAttachMade} />}
      </div>
      <p id="attach-hint" className="hint">
        Attach an inventory of your data files (.json), which holds their names, sizes, formats
        and table column headings but not the data themselves
        {documents
          ? ", or a document about your data, such as a protocol, codebook or data management " +
            "plan (.txt, .md, .docx or a PDF with text, up to 1 MB)"
          : ". This deployment does not keep documents about your data"}
        . Never attach the data themselves: your data are not uploaded.
      </p>
    </>
  );
}
