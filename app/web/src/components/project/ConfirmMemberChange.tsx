/**
 * Asking before a member is removed, or before the person leaves (docs/specs/projects.md, Roles):
 * a button that opens a dialog saying what happens. Removal takes effect at once and cannot be
 * undone from this page, though an owner may add the person again; what they did in the project
 * keeps their name.
 */

import type { LucideIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";

export function ConfirmMemberChange({
  label,
  icon,
  title,
  children,
  confirm,
  busy,
  onConfirm,
}: {
  /** What the button that opens the dialog says. */
  label: React.ReactNode;
  icon?: LucideIcon;
  title: string;
  /** What the dialog says will happen. */
  children: React.ReactNode;
  /** What the button that makes the change says. */
  confirm: string;
  busy: boolean;
  onConfirm: () => void;
}) {
  const [isOpen, setOpen] = useState(false);
  return (
    <DialogTrigger isOpen={isOpen} onOpenChange={setOpen}>
      <Button variant="quiet" size="small" {...(icon ? { icon } : {})}>
        {label}
      </Button>
      <ModalDialog title={title}>
        {children}
        <div className="project-rename-actions">
          <Button
            variant="danger"
            isPending={busy}
            onPress={() => {
              setOpen(false);
              onConfirm();
            }}
          >
            {confirm}
          </Button>
          <Button variant="secondary" onPress={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </ModalDialog>
    </DialogTrigger>
  );
}
