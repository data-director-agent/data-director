/**
 * Revising the inventory a project holds (docs/specs/projects.md): a button that opens the
 * inventory editor on it, and saves the result as the project's new inventory. The researcher may
 * instead read a new scan of the same dataset, onto which what they said before is carried by
 * path (`carryOver`), and see what the scan changed. Saving adds a whole new inventory; the
 * earlier one stays in the project's log, and the store records which one it revises.
 */

import {
  applyEdits,
  asInventory,
  carryOver,
  diffInventories,
  NotAnInventory,
  parseInventory,
  type FileInventory,
} from "@data-director/inventory";
import { Check, Pencil } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { useProjectApi, type SavedInventory } from "../../project/api";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { startHistory, type EditHistory } from "./history";
import { InventoryEditor, type Rescan } from "./InventoryEditor";

type State =
  | { status: "loading" }
  | { status: "failed"; message: string }
  | { status: "ready"; stored: FileInventory; base: FileInventory; history: EditHistory; rescan?: Rescan };

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function InventoryEditDialog({
  projectId,
  onSaved,
}: {
  projectId: string;
  onSaved?: ((saved: SavedInventory) => void) | undefined;
}) {
  const [isOpen, setOpen] = useState(false);
  return (
    <>
      <Button size="small" variant="quiet" icon={Pencil} onPress={() => setOpen(true)}>
        Edit inventory
      </Button>
      {isOpen && (
        <Editing
          projectId={projectId}
          onClose={() => setOpen(false)}
          onSaved={(saved) => {
            setOpen(false);
            onSaved?.(saved);
          }}
        />
      )}
    </>
  );
}

function Editing({
  projectId,
  onClose,
  onSaved,
}: {
  projectId: string;
  onClose: () => void;
  onSaved: (saved: SavedInventory) => void;
}) {
  const api = useProjectApi();
  const fileId = useId();
  const [state, setState] = useState<State>({ status: "loading" });
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api.inventory(projectId, controller.signal).then(
      (value) => {
        try {
          const stored = asInventory(value);
          setState({ status: "ready", stored, base: stored, history: startHistory() });
        } catch (e) {
          setState({ status: "failed", message: message(e) });
        }
      },
      (e: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: "failed", message: `The inventory could not be read: ${message(e)}` });
        }
      },
    );
    return () => controller.abort();
  }, [api, projectId]);

  async function readScan(file: File, stored: FileInventory) {
    setProblem(null);
    try {
      const rescan = parseInventory(await file.text());
      const { edits, orphaned } = carryOver(stored, rescan);
      setState({
        status: "ready",
        stored,
        base: rescan,
        history: startHistory(edits),
        rescan: { diff: diffInventories(stored, rescan), orphaned },
      });
    } catch (e) {
      setProblem(e instanceof NotAnInventory ? e.message : message(e));
    }
  }

  async function save(document: FileInventory) {
    setSaving(true);
    setProblem(null);
    try {
      onSaved(await api.saveInventory(projectId, document));
    } catch (e) {
      setProblem(`The inventory was not saved: ${message(e)}`);
      setSaving(false);
    }
  }

  const ready = state.status === "ready" ? state : null;
  // Nothing to save until something is edited or a new scan is read.
  const unchanged = !ready || (!ready.rescan && ready.history.past.length === 0);
  return (
    <ModalDialog
      title="Edit the project's inventory"
      isOpen
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      footer={
        ready && (
          <>
            {problem && <p role="alert">{problem}</p>}
            <Button onPress={onClose}>Cancel</Button>
            <Button
              variant="primary"
              icon={Check}
              isDisabled={unchanged}
              isPending={saving}
              onPress={() => void save(applyEdits(ready.base, ready.history.present))}
            >
              Save as the project&apos;s inventory
            </Button>
          </>
        )
      }
    >
      {state.status === "loading" && <p role="status">Reading the inventory…</p>}
      {state.status === "failed" && <p role="alert">{state.message}</p>}
      {ready && (
        <>
          <div className="callout">
            <p>
              Saving keeps a new version of the inventory in the project; the earlier one stays in
              its history. Anything you write is kept and shown to agents, as file names and column
              headings are.
            </p>
            <div className="field">
              <label htmlFor={fileId}>Replace with a new scan of the same folder</label>
              <p className="hint muted" id={`${fileId}-hint`}>
                The file <code>dd-inventory</code> wrote. What you said about files is carried over.
              </p>
              <input
                id={fileId}
                type="file"
                accept=".json,application/json"
                aria-describedby={`${fileId}-hint`}
                onChange={(e) => {
                  const file = e.currentTarget.files?.[0];
                  if (file) void readScan(file, ready.stored);
                }}
              />
            </div>
          </div>
          <InventoryEditor
            base={ready.base}
            history={ready.history}
            onHistory={(history) => setState({ ...ready, history })}
            rescan={ready.rescan}
          />
        </>
      )}
    </ModalDialog>
  );
}
