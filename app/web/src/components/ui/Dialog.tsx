/**
 * The shell's modal dialog: React Aria's ModalOverlay, Modal and Dialog, styled from the tokens.
 * Put it in a `DialogTrigger` after the button that opens it. React Aria keeps focus inside while
 * it is open, closes it on Escape or a press outside, and returns focus to the button.
 *
 * ```tsx
 * <DialogTrigger>
 *   <Button>View</Button>
 *   <ModalDialog title="What the inventory holds">…</ModalDialog>
 * </DialogTrigger>
 * ```
 */

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";

import { Button } from "./Button";
import "./Dialog.css";

export { DialogTrigger } from "react-aria-components";

/**
 * `children` may be a function of `close`, for a dialog whose last step closes it, such as one
 * that ends by choosing a file.
 */
export function ModalDialog({
  title,
  children,
}: {
  title: string;
  children: ReactNode | ((close: () => void) => ReactNode);
}) {
  return (
    <ModalOverlay className="dialog-overlay" isDismissable>
      <Modal className="dialog-modal">
        <Dialog className="dialog">
          {({ close }) => (
            <>
              <div className="dialog-header">
                <Heading slot="title" level={2}>
                  {title}
                </Heading>
                <Button slot="close" variant="quiet" icon={X} aria-label="Close" />
              </div>
              <div className="dialog-body">
                {typeof children === "function" ? children(close) : children}
              </div>
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
