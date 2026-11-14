/**
 * Revising the inventory a project holds (docs/specs/projects.md): a button that opens the
 * inventory editor on it, and saves the result as the project's new inventory. The researcher may
 * also update it with a new scan: of the folder it was made from, of one of its folders, or of a
 * folder it does not have yet, which is added beside the others. Only the folder scanned is
 * replaced (`withPart`); what they said before is carried by path (`carryOver`), and they see what
 * the scan changed. Saving adds a whole new inventory; the earlier one stays in the project's log,
 * and the store records which one it revises.
 */

import {
  applyEdits,
  asInventory,
  asParts,
  carryOver,
  diffInventories,
  NotAnInventory,
  NotAPartFolder,
  parseInventory,
  partFolderProblem,
  partsOf,
  withPart,
  type FileInventory,
} from "@data-director/inventory";
import { Check, Pencil } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { useProjectApi, type SavedInventory } from "../../project/api";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { startHistory, type EditHistory } from "./history";
import { InventoryEditor, type Rescan } from "./InventoryEditor";

/**
 * Which folder a new scan is of: the one an inventory without folders was made from, one of the
 * inventory's folders, or a folder it does not have yet. Adding a folder to an inventory without
 * folders first names the folder it has (`existing`).
 */
export type ScanTarget =
  | { kind: "whole" }
  | { kind: "folder"; folder: string }
  | { kind: "new"; folder: string; existing?: string };

/** Why `target` cannot take a scan of `stored`, in a sentence, or null when it can. */
export function targetProblem(stored: FileInventory, target: ScanTarget): string | null {
  if (target.kind !== "new") return null;
  const folders = (partsOf(stored) ?? []).map((p) => p.part_folder);
  const name = partFolderProblem(target.folder);
  if (name) return `The new folder: ${name}`;
  if (folders.includes(target.folder)) {
    return `The inventory already has ${target.folder}: choose it to update it.`;
  }
  if (!folders.length) {
    const existing = partFolderProblem(target.existing ?? "");
    if (existing) return `The folder the inventory already has: ${existing}`;
    if (target.existing === target.folder) return "Give the two folders different names.";
  }
  return null;
}

/**
 * `scan` applied to `stored` as `target` says: `previous`, the stored inventory as the new one
 * names its files (its folder named, when one is added to an inventory without folders), and
 * `next`, the inventory with the scan in place.
 */
export function applyScan(
  stored: FileInventory,
  scan: FileInventory,
  target: ScanTarget,
): { previous: FileInventory; next: FileInventory } {
  if (target.kind === "whole") return { previous: stored, next: scan };
  const previous =
    target.kind === "new" && !partsOf(stored) ? asParts(stored, target.existing ?? "") : stored;
  return { previous, next: withPart(previous, scan, target.folder) };
}

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

  async function readScan(file: File, stored: FileInventory, target: ScanTarget) {
    setProblem(null);
    try {
      const { previous, next } = applyScan(stored, parseInventory(await file.text()), target);
      const { edits, orphaned } = carryOver(previous, next);
      setState({
        status: "ready",
        stored,
        base: next,
        history: startHistory(edits),
        rescan: { diff: diffInventories(previous, next), orphaned },
      });
    } catch (e) {
      setProblem(e instanceof NotAnInventory || e instanceof NotAPartFolder ? e.message : message(e));
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
            <ScanChooser stored={ready.stored} onScan={(file, target) => void readScan(file, ready.stored, target)} />
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

const NEW = "\u0000new";
const WHOLE = "\u0000whole";

/**
 * Choosing which folder a new scan is of, then the scan. The file can be chosen once the names
 * a new folder needs are given.
 */
function ScanChooser({
  stored,
  onScan,
}: {
  stored: FileInventory;
  onScan: (file: File, target: ScanTarget) => void;
}) {
  const id = useId();
  const folders = (partsOf(stored) ?? []).map((p) => p.part_folder);
  const [choice, setChoice] = useState(folders[0] ?? WHOLE);
  const [folder, setFolder] = useState("");
  const [existing, setExisting] = useState("");
  const target: ScanTarget =
    choice === WHOLE
      ? { kind: "whole" }
      : choice === NEW
        ? { kind: "new", folder: folder.trim(), ...(folders.length ? {} : { existing: existing.trim() }) }
        : { kind: "folder", folder: choice };
  const problem = choice === NEW && (folder || existing) ? targetProblem(stored, target) : null;
  const ready = targetProblem(stored, target) === null;
  return (
    <fieldset className="field">
      <legend>Update with a new scan</legend>
      <p className="hint muted" id={`${id}-hint`}>
        The file <code>dd-inventory</code> wrote. Only the folder you choose is replaced; what you
        said about its files is carried over, and the other folders stay as they are.
      </p>
      <label htmlFor={`${id}-folder`}>Scan of</label>
      <select id={`${id}-folder`} value={choice} onChange={(e) => setChoice(e.target.value)}>
        {folders.length === 0 && <option value={WHOLE}>The folder the inventory was made from</option>}
        {folders.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
        <option value={NEW}>A folder the inventory does not have yet</option>
      </select>
      {choice === NEW && (
        <>
          <label htmlFor={`${id}-new`}>Name of the new folder</label>
          <input id={`${id}-new`} type="text" value={folder} onChange={(e) => setFolder(e.target.value)} />
          {folders.length === 0 && (
            <>
              <label htmlFor={`${id}-existing`}>Name for the folder the inventory already has</label>
              <p className="hint muted" id={`${id}-existing-hint`}>
                Its files will be listed under this name, beside the new folder.
              </p>
              <input
                id={`${id}-existing`}
                type="text"
                aria-describedby={`${id}-existing-hint`}
                value={existing}
                onChange={(e) => setExisting(e.target.value)}
              />
            </>
          )}
          {problem && <p className="hint">{problem}</p>}
        </>
      )}
      <label htmlFor={`${id}-file`}>New scan</label>
      <input
        id={`${id}-file`}
        type="file"
        accept=".json,application/json"
        aria-describedby={`${id}-hint`}
        disabled={!ready}
        onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          if (file) onScan(file, target);
        }}
      />
    </fieldset>
  );
}
