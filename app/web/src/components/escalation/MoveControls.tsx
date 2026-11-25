/**
 * The moves a person may make on an escalation, as the harness lists them
 * (`permitted_moves`, docs/specs/stewardship.md, invariant 4): one control each, on whichever
 * side the reader is. A move that needs a note, or may carry one, opens a short form first; one
 * the harness refuses is said with why, not hidden (docs/ui/steward-escalation-flows.md, flow C).
 * A move that names a target, `reassign` or `transfer`, asks whom to pass it to from the
 * colleagues or teams the harness lists (flow G).
 * The shell derives no move from the state.
 *
 * A control is disabled, not pending, while its move is made: the move usually removes it, and a
 * pending button's busy announcement would then name a label that is gone.
 */

import { useState } from "react";

import type { Escalation } from "../../project/escalations";
import type { MoveName, PermittedMove } from "../../project/steward";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";
import { NoteField } from "./NoteField";
import { TargetField } from "./TargetField";
import { MOVE_CONTROL, MOVE_TARGET, moveRefusalSaid } from "./wording";

export function MoveControls({
  escalation,
  onMove,
  context,
}: {
  escalation: Escalation;
  /** Makes the move; rejects with what went wrong. */
  onMove(move: MoveName, note?: string, to?: string): Promise<unknown>;
  /** Names what the controls act on, for a screen reader, where several are on one page. */
  context?: string;
}) {
  const announce = useAnnounce();
  const [writing, setWriting] = useState<PermittedMove | null>(null);
  const [note, setNote] = useState("");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const permitted = escalation.permitted_moves.filter((m) => m.permitted);
  const refused = escalation.permitted_moves.filter((m) => !m.permitted);

  async function make(move: MoveName, withNote?: string, target?: string) {
    setBusy(true);
    setError(null);
    try {
      await onMove(move, withNote, target);
      setWriting(null);
      setNote("");
      announce(MOVE_CONTROL[move].done);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const hidden = context ? <span className="visually-hidden"> {context}</span> : null;
  return (
    <div className="escalation-moves">
      {writing ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const text = note.trim();
            if (writing.note === "required" && !text) return;
            void make(writing.move, text || undefined, writing.targets ? to : undefined);
          }}
        >
          {writing.targets && (
            <TargetField
              label={MOVE_TARGET[writing.move] ?? "Pass it to"}
              targets={writing.targets}
              value={to}
              onChange={setTo}
            />
          )}
          {writing.note !== "none" && (
            <NoteField
              label={MOVE_CONTROL[writing.move].field}
              value={note}
              onChange={setNote}
              required={writing.note === "required"}
            />
          )}
          <Button type="submit" size="small" variant="primary" isDisabled={busy}>
            {MOVE_CONTROL[writing.move].label}
            {hidden}
          </Button>{" "}
          <Button size="small" variant="quiet" onPress={() => setWriting(null)}>
            Cancel
          </Button>
        </form>
      ) : (
        permitted.length > 0 && (
          <p className="escalation-move-list">
            {permitted.map((m) => (
              <Button
                key={m.move}
                size="small"
                variant={m.move === "take" ? "primary" : undefined}
                isDisabled={busy}
                onPress={() => {
                  if (m.note === "none" && !m.targets) {
                    void make(m.move);
                    return;
                  }
                  setTo(m.targets?.[0]?.id ?? "");
                  setWriting(m);
                }}
              >
                {MOVE_CONTROL[m.move].label}
                {hidden}
              </Button>
            ))}
          </p>
        )
      )}
      {refused.length > 0 && (
        <p className="hint">{moveRefusalSaid(refused[0]?.refusal ?? "")}</p>
      )}
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
    </div>
  );
}
