/**
 * Starting a project (docs/specs/app.md, rule 27): a dialog with one optional field, the
 * project's name. **Create project** sends `POST /api/projects`; the project the server answers
 * with becomes the active one and the shell goes to its workspace, where Data Director speaks
 * first with the intake (rule 25) before the researcher has typed anything.
 *
 * A refusal or failure is said in the dialog, which keeps what was typed. The page opens the
 * dialog itself (`isOpen`), as from the project switcher, whose choice is not a button.
 */

import "./NewProjectDialog.css";

import { type FormEvent, useState } from "react";

import { useActiveProject } from "../../project/active";
import { useProjectApi } from "../../project/api";
import { navigate } from "../../route";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { PROJECT_TITLE_MAX } from "./ProjectRename";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function NewProjectDialog({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
}) {
  const api = useProjectApi();
  const { setProjectId, reloadProjects } = useActiveProject();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = (next: boolean) => {
    if (saving) return;
    if (next) {
      setDraft("");
      setError(null);
    }
    onOpenChange(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    const title = draft.trim();
    setSaving(true);
    setError(null);
    api.create(title || undefined).then(
      (created) => {
        setSaving(false);
        setProjectId(created.project_id);
        reloadProjects();
        onOpenChange(false);
        navigate("/");
      },
      (e: unknown) => {
        setSaving(false);
        setError(`Data Director could not create the project: ${message(e)}`);
      },
    );
  };

  return (
    <ModalDialog title="New project" isOpen={isOpen} onOpenChange={open}>
      <form className="new-project" onSubmit={submit}>
        <div className="field">
          <label htmlFor="new-project-title">Project name (optional)</label>
          <p className="hint" id="new-project-hint">
            Leave it blank and Data Director suggests a name from your first conversation.
          </p>
          <input
            type="text"
            id="new-project-title"
            aria-describedby="new-project-hint"
            maxLength={PROJECT_TITLE_MAX}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            // The dialog opens to name the project, so the field takes focus.
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
          />
        </div>
        {error && (
          <div role="alert" className="callout status-danger">
            <p>{error}</p>
          </div>
        )}
        <div className="new-project-actions">
          <Button type="submit" variant="primary" isDisabled={saving}>
            {saving ? "Creating…" : "Create project"}
          </Button>
          <Button variant="secondary" onPress={() => open(false)} isDisabled={saving}>
            Cancel
          </Button>
        </div>
      </form>
    </ModalDialog>
  );
}
