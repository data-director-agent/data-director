/**
 * Deleting a conversation (docs/specs/app.md, rule 30; docs/specs/projects.md, invariants 29 to
 * 31): a small button beside the conversation that opens a dialog saying what deleting does and
 * what it does not, then deletes. Deleting hides the conversation from every list and erases
 * nothing; whoever started it, or the project's owner, may restore it from the project's page
 * until the date the dialog names. Since it can be restored, no name need be typed.
 */

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useConversationApi } from "../../conversation/api";
import { restorableUntil } from "../../project/name";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";

export function DeleteConversation({
  conversationId,
  title,
  restoreDays,
  onDeleted,
}: {
  conversationId: string;
  title: string;
  /** For how many days it may be restored; 0 makes deletion final. Unknown if not given. */
  restoreDays?: number | undefined;
  onDeleted: (conversationId: string) => void;
}) {
  const api = useConversationApi();
  const [isOpen, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const until = restoreDays === undefined ? undefined : restorableUntil(restoreDays);

  const open = (next: boolean) => {
    if (next) setError(null);
    setOpen(next);
  };

  const remove = () => {
    setDeleting(true);
    api.remove(conversationId).then(
      () => {
        setDeleting(false);
        setOpen(false);
        onDeleted(conversationId);
      },
      (e: unknown) => {
        setDeleting(false);
        setError(`Data Director could not delete this conversation: ${errorMessage(e)}`);
      },
    );
  };

  return (
    <DialogTrigger isOpen={isOpen} onOpenChange={open}>
      <Button
        variant="quiet"
        size="small"
        icon={Trash2}
        className="conversation-delete"
        aria-label={`Delete conversation: ${title}`}
      />
      <ModalDialog
        title="Delete conversation"
        footer={
          <div className="conversation-delete-actions">
            <Button variant="danger" onPress={remove} isPending={deleting}>
              {deleting ? "Deleting…" : "Delete conversation"}
            </Button>
            <Button variant="secondary" onPress={() => open(false)}>
              Cancel
            </Button>
          </div>
        }
      >
        <p>
          <strong>{title}</strong> will leave every list, for you and for everyone working on its
          project, and will take no new message.
        </p>
        <ul>
          <li>Nothing is erased: its record, and what it added to the project, are kept.</li>
          <li>
            {until === undefined
              ? "You can restore it from the project's page for a time this deployment sets."
              : until
                ? `You can restore it from the project's page until ${until}.`
                : "This deployment does not let a deleted conversation be restored."}
          </li>
        </ul>
        {error && (
          <div role="alert" className="callout status-danger">
            <p>{error}</p>
          </div>
        )}
      </ModalDialog>
    </DialogTrigger>
  );
}
