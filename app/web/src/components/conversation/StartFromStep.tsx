/**
 * Starting a conversation from a step of the data journey: the prompts an empty conversation
 * offers, and the dialog that asks leave before a message being written is replaced
 * (docs/specs/app.md, "The phases").
 */

import type { FlowStep } from "../../flow/types";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import { SuggestedPrompts } from "./SuggestedPrompts";

export function StartFromStep({
  offered,
  replacing,
  onChoose,
  onCancel,
}: {
  /** The steps to offer as prompts, or null when none should show. */
  offered: FlowStep[] | null;
  /** The step whose prompt waits on leave to replace the message. */
  replacing: FlowStep | null;
  onChoose: (step: FlowStep) => void;
  onCancel: () => void;
}) {
  return (
    <>
      {offered && <SuggestedPrompts steps={offered} onChoose={onChoose} />}
      <ModalDialog
        title="Replace your message?"
        isOpen={replacing !== null}
        onOpenChange={(open) => open || onCancel()}
        footer={
          <>
            <Button variant="primary" onPress={() => replacing && onChoose(replacing)}>
              Replace it
            </Button>
            <Button onPress={onCancel}>Keep my message</Button>
          </>
        }
      >
        <p>
          Starting a conversation about {replacing?.label} puts a suggested message in the box, in
          place of what you have written and attached.
        </p>
      </ModalDialog>
    </>
  );
}
