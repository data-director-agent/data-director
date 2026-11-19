/**
 * Deleting a project (docs/specs/projects.md, invariants 22 to 26, "Deletion and retention"): a
 * button that opens a dialog saying what deleting does and what it does not, and asks the owner to
 * type the project's name before it deletes. Deleting hides the project and removes nothing; an
 * owner may restore it from the Projects page until the date the dialog names. The server checks
 * the name too, so no page can skip the guard.
 */

import { Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import { useActiveProject } from "../../project/active";
import { useProjectApi } from "../../project/api";
import { restorableUntil } from "../../project/name";
import { navigate } from "../../route";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function DeleteProject({
  projectId,
  name,
  typedName,
  restoreDays,
}: {
  projectId: string;
  /** The name the page shows. */
  name: string;
  /** What the owner must type: the project's title, or its identifier while it has none. */
  typedName: string;
  /** For how many days an owner may restore it; 0 makes deletion final. Unknown if not given. */
  restoreDays: number | undefined;
}) {
  const api = useProjectApi();
  const { projectId: activeId, setProjectId, reloadProjects } = useActiveProject();
  const [isOpen, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const until = restoreDays === undefined ? undefined : restorableUntil(restoreDays);
  const matches = typed.trim() === typedName;

  const open = (next: boolean) => {
    if (next) {
      setTyped("");
      setError(null);
    }
    setOpen(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!matches) return;
    setDeleting(true);
    api.remove(projectId, typed.trim()).then(
      () => {
        setDeleting(false);
        setOpen(false);
        if (activeId === projectId) setProjectId(null);
        reloadProjects();
        navigate("/projects");
      },
      (e: unknown) => {
        setDeleting(false);
        setError(`Data Director could not delete this project: ${message(e)}`);
      },
    );
  };

  return (
    <DialogTrigger isOpen={isOpen} onOpenChange={open}>
      <Button variant="danger" size="small" icon={Trash2}>
        Delete project
      </Button>
      <ModalDialog title="Delete project">
        <form className="project-delete" onSubmit={submit}>
          <p>
            <strong>{name}</strong> will leave every list, with its conversations, for you and for
            everyone working on it, and it will take no new work.
          </p>
          <ul>
            <li>Nothing is erased: its record, documents and decisions are kept.</li>
            <li>A deposit package already built or downloaded is not recalled.</li>
            <li>
              {until === undefined
                ? "You can restore it from the Projects page for a time this deployment sets."
                : until
                  ? `You can restore it from the Projects page until ${until}.`
                  : "This deployment does not let a deleted project be restored."}
            </li>
          </ul>
          <div className="field">
            <label htmlFor="project-delete-name">The project&apos;s name, to confirm</label>
            <p className="hint" id="project-delete-hint">
              Type <code>{typedName}</code> exactly.
            </p>
            <input
              type="text"
              id="project-delete-name"
              aria-describedby="project-delete-hint"
              autoComplete="off"
              spellCheck={false}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              // The dialog opens to type the name, so the field takes focus.
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
            <Button type="submit" variant="danger" isDisabled={!matches || deleting}>
              {deleting ? "Deleting…" : "Delete project"}
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
