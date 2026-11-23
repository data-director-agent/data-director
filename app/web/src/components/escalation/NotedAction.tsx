/**
 * A steward's step that carries a note (docs/specs/stewardship.md, invariant 6): a button that
 * opens a short form for the note, and sends it. What it did is announced; what the server refused
 * is said in an alert beside the form.
 *
 * The send button is disabled, not pending, while the step is sent: the form closes once it is,
 * and a pending button's busy announcement would then name a label that is gone.
 */

import { useState } from "react";

import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";
import { NoteField } from "./NoteField";

export interface Noted {
  /** The button's label, which also sends the form. */
  label: string;
  /** What the note is for. */
  field: string;
  /** What is announced once it is done. */
  done: string;
}

export function NotedAction({
  said,
  send,
  onDone,
  variant,
}: {
  said: Noted;
  send: (note: string) => Promise<unknown>;
  onDone: () => void;
  variant?: "primary" | "danger";
}) {
  const announce = useAnnounce();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!open) {
    return (
      <Button size="small" variant={variant} onPress={() => setOpen(true)}>
        {said.label}
      </Button>
    );
  }
  return (
    <form
      className="noted-action"
      onSubmit={(event) => {
        event.preventDefault();
        if (!note.trim()) return;
        setBusy(true);
        setError(null);
        send(note.trim())
          .then(
            () => {
              setOpen(false);
              setNote("");
              announce(said.done);
              onDone();
            },
            (e: unknown) => setError(errorMessage(e)),
          )
          .finally(() => setBusy(false));
      }}
    >
      <NoteField label={said.field} value={note} onChange={setNote} />
      <Button type="submit" size="small" variant="primary" isDisabled={busy}>
        {said.label}
      </Button>{" "}
      <Button size="small" variant="quiet" onPress={() => setOpen(false)}>
        Cancel
      </Button>
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
    </form>
  );
}
