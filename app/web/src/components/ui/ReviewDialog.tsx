/**
 * A dialog in which something is checked before it is attached: an inventory or a document. Its
 * footer offers **Cancel** and one button that attaches; closing it any other way discards what
 * it shows, so nothing is attached by accident.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./Button";
import { ModalDialog } from "./Dialog";

export interface AttachAction {
  label: string;
  icon: LucideIcon;
  onPress: () => void;
  isDisabled?: boolean;
  isPending?: boolean;
}

export function ReviewDialog({
  title,
  isOpen,
  onDiscard,
  attach,
  children,
}: {
  title: string;
  isOpen: boolean;
  onDiscard: () => void;
  attach: AttachAction;
  children: ReactNode;
}) {
  return (
    <ModalDialog
      title={title}
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onDiscard();
      }}
      footer={
        isOpen && (
          <>
            <Button onPress={onDiscard}>Cancel</Button>
            <Button
              variant="primary"
              icon={attach.icon}
              isDisabled={attach.isDisabled ?? false}
              isPending={attach.isPending ?? false}
              onPress={attach.onPress}
            >
              {attach.label}
            </Button>
          </>
        )
      }
    >
      {children}
    </ModalDialog>
  );
}
