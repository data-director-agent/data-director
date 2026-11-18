/**
 * A conversation turn's run as its stream arrives (#69, #949): its stages, a Cancel control while
 * it runs, the events the shell could not draw, and, once it has ended without finishing, what it
 * came to. A run that finished is shown as a turn of the transcript instead.
 */

import { X } from "lucide-react";

import { hasEnded, type RunState } from "../../run/reduce";
import { Button } from "../ui/Button";
import { RunEnded } from "./RunEnded";
import { Stages } from "./Stages";
import { UnrecognisedEvents } from "./UnrecognisedEvents";

export function LiveRun({
  run,
  cancelling,
  onCancel,
  idPrefix,
}: {
  run: RunState;
  cancelling: boolean;
  onCancel: () => void;
  idPrefix: string;
}) {
  return (
    <div className="live-run">
      <h3 className="visually-hidden">Progress and outcome</h3>
      <Stages run={run} />
      {!hasEnded(run) && (
        <p>
          <Button icon={X} isPending={cancelling} onPress={onCancel}>
            {cancelling ? "Cancelling…" : "Cancel the run"}
          </Button>
        </p>
      )}
      <UnrecognisedEvents run={run} />
      <RunEnded run={run} idPrefix={idPrefix} />
    </div>
  );
}
