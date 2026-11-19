/**
 * Renaming a project (docs/specs/projects.md): a button that opens a dialog with the project's
 * name to edit. A person's name is the project's for good; the Data Director names a project only
 * while no person has. The page shows the name the server answers with, never one it assumed.
 */

import { Pencil } from "lucide-react";
import { type FormEvent, useState } from "react";

import { useProjectApi } from "../../project/api";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";

// dd_harness.projects.TITLE_MAX_LENGTH
export const PROJECT_TITLE_MAX = 200;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ProjectRename({
  projectId,
  name,
  named,
  onRenamed,
}: {
  projectId: string;
  /** The name the page shows now. */
  name: string;
  /** Who gave that name: a person, the Data Director's model, or nobody yet. */
  named: "researcher" | "model" | null;
  onRenamed: () => void;
}) {
  const api = useProjectApi();
  const [isOpen, setOpen] = useState(false);
  const [draft, setDraft] = useState(name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = (next: boolean) => {
    if (next) {
      setDraft(name);
      setError(null);
    }
    setOpen(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const title = draft.trim();
    if (!title) {
      setError("Give the project a name.");
      return;
    }
    setSaving(true);
    api.rename(projectId, title).then(
      () => {
        setSaving(false);
        setOpen(false);
        onRenamed();
      },
      (e: unknown) => {
        setSaving(false);
        setError(`Data Director could not rename this project: ${message(e)}`);
      },
    );
  };

  const hint =
    named === "model"
      ? "The Data Director suggested this name from your conversation. A name you give replaces it, and the Data Director will not change it again."
      : named === "researcher"
        ? "Everyone working on the project sees this name."
        : "The project has no name yet. A name you give is kept; the Data Director will not change it.";

  return (
    <DialogTrigger isOpen={isOpen} onOpenChange={open}>
      <Button variant="quiet" size="small" icon={Pencil}>
        Rename project
      </Button>
      <ModalDialog title="Rename project">
        <form className="project-rename" onSubmit={submit}>
          <div className="field">
            <label htmlFor="project-rename-title">Project name</label>
            <p className="hint" id="project-rename-hint">
              {hint}
            </p>
            <input
              type="text"
              id="project-rename-title"
              aria-describedby="project-rename-hint"
              required
              maxLength={PROJECT_TITLE_MAX}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              // The dialog opens to edit the name, so the field takes focus.
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus
            />
          </div>
          {error && (
            <div role="alert" className="callout status-danger">
              <p>{error}</p>
            </div>
          )}
          <div className="project-rename-actions">
            <Button type="submit" variant="primary" isDisabled={saving}>
              {saving ? "Saving…" : "Save name"}
            </Button>
            <Button variant="secondary" onPress={() => open(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </ModalDialog>
    </DialogTrigger>
  );
}
