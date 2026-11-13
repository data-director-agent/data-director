/**
 * Adding an inventory to a project from outside a conversation (docs/specs/projects.md): the
 * project page and the workspace's project panel offer **Add an inventory**, beside **Make an
 * inventory**, which says how to make one. A file chosen is read, then opened in the same check
 * as one attached to a message (`InventoryReviewDialog`, #472), and only when the researcher
 * confirms is it saved, as the project's latest inventory (`POST /api/projects/{id}/inventory`),
 * revising any the project holds. Until then nothing is stored. What happened is said in the
 * component's live region, which is in the page from the start.
 */

import { Check, Upload } from "lucide-react";
import { useState } from "react";
import { FileTrigger } from "react-aria-components";

import {
  type AttachedInventory,
  NotAnInventory,
  readInventory,
} from "../../conversation/inventory";
import { type SavedInventory, useProjectApi } from "../../project/api";
import { Button } from "../ui/Button";
import { InventoryReviewDialog } from "./InventoryReviewDialog";
import { MakeInventoryDialog } from "./MakeInventoryDialog";

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function AddInventory({
  projectId,
  replacing = false,
  onSaved,
}: {
  projectId: string;
  /** True when the project already holds an inventory, which the new one then revises. */
  replacing?: boolean;
  onSaved?: ((saved: SavedInventory) => void) | undefined;
}) {
  const api = useProjectApi();
  const [pending, setPending] = useState<AttachedInventory | null>(null);
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<{ text: string; ok: boolean } | null>(null);

  async function choose(file: File | undefined) {
    if (!file) return;
    try {
      setPending(readInventory(await file.text(), file.name));
      setSaid(null);
    } catch (e) {
      setSaid({
        ok: false,
        text: e instanceof NotAnInventory ? e.message : `Data Director could not read ${file.name}: ${message(e)}`,
      });
    }
  }

  async function save(checked: AttachedInventory) {
    setSaving(true);
    try {
      const saved = await api.saveInventory(projectId, checked.document);
      setPending(null);
      setSaid({ ok: true, text: "Inventory added to the project." });
      onSaved?.(saved);
    } catch (e) {
      // The check stays open, so that nothing the researcher chose to leave out is lost.
      setSaid({ ok: false, text: `The inventory was not added: ${message(e)}` });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <span className="add-inventory">
        <FileTrigger
          acceptedFileTypes={["application/json", ".json"]}
          onSelect={(files) => void choose(files?.[0])}
        >
          <Button icon={Upload} isPending={saving}>
            {replacing ? "Replace the inventory" : "Add an inventory"}
          </Button>
        </FileTrigger>{" "}
        <MakeInventoryDialog onAttach={(file) => void choose(file)} />
      </span>
      {/* Not a `status` role, which the page around it already has; it only needs to be announced. */}
      <span aria-live="polite">{said?.ok !== false && said?.text}</span>
      {said?.ok === false && <span role="alert">{said.text}</span>}
      <InventoryReviewDialog
        pending={pending}
        attachLabel="Add this inventory"
        attachIcon={Check}
        isPending={saving}
        onAttach={(checked) => void save(checked)}
        onDiscard={() => {
          if (!saving) setPending(null);
        }}
      />
    </>
  );
}
