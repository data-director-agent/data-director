/**
 * The second confirmation before a version that still has gaps is approved as it is (#1282).
 * Approval is final (`docs/specs/projects.md`, invariant 11) and the deposit package takes the
 * latest approved version, so the person is told what they are accepting as missing, by count,
 * and approves only by pressing the button that names it.
 *
 * React Aria's modal moves focus into the dialog when it opens, keeps it there, and closes it on
 * Escape, returning focus to the button that submitted the form. Closing it any way but the
 * approve button records nothing.
 */

import { Check } from "lucide-react";

import type { VersionGaps } from "../../project/gaps";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";

export function ApproveWithGaps({
  version,
  gaps,
  isOpen,
  onCancel,
  onApprove,
}: {
  version: number;
  gaps: VersionGaps;
  isOpen: boolean;
  onCancel: () => void;
  onApprove: () => void;
}) {
  return (
    <ModalDialog
      title={`Approve version ${version} with ${gaps.gapWords}?`}
      isOpen={isOpen}
      onOpenChange={(open) => !open && onCancel()}
      footer={
        <div className="project-rename-actions">
          <Button variant="primary" icon={Check} onPress={onApprove}>
            Approve with {gaps.gapWords}
          </Button>
          <Button variant="secondary" onPress={onCancel}>
            Go back
          </Button>
        </div>
      }
    >
      <p>
        Version {version} has {gaps.gapWords} and {gaps.openWords}. Approved as it is, it keeps
        every gap.
      </p>
      <p>
        An approval cannot be undone: the version stays approved, and the deposit package takes the
        latest approved version. To fill the gaps first, go back and answer the questions, then ask
        for a new draft, or edit the text and approve your version.
      </p>
    </ModalDialog>
  );
}
