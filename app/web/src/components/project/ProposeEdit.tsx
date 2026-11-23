/**
 * A data steward's edit to a document (docs/specs/stewardship.md, invariant 6): **Propose an
 * edit** opens the latest version's text to change, and sends it as a new `proposed` version,
 * marked as the steward's, which the project's owners approve or reject. Nothing is approved here.
 * While the steward edits, the reader's preview shows their text (`onEditing`), as for a
 * researcher's own edit.
 *
 * The edit names the version it was made from and that version's digest, so that the server
 * refuses it if the document moved on meanwhile; the reader then reads the project again and
 * says so (`onStale`). Text stored with CRLF line endings gets them back.
 */

import { PencilLine } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { type DocumentVersion, digestOf } from "../../project/api";
import { useStewardApi } from "../../project/steward";
import { EscalationRefused } from "../../project/escalations";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";

export function ProposeEdit({
  projectId,
  name,
  version,
  isLatest,
  onEditing,
  onProposed,
  onStale,
}: {
  projectId: string;
  name: string;
  /** The latest version, which the edit is made from. */
  version: DocumentVersion;
  /** Whether `version` is the latest; an edit is made only from the latest. */
  isLatest: boolean;
  onEditing: (text: string | null) => void;
  /** Reads the project again once the version is proposed. */
  onProposed: () => void;
  /** Says why the server refused it, after reading the project again. */
  onStale: (detail: string) => Promise<void>;
}) {
  const api = useStewardApi();
  const announce = useAnnounce();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(version.text);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lineEnding = version.text.includes("\r\n") ? "\r\n" : null;

  useEffect(() => {
    onEditing(open ? text : null);
  }, [open, text, onEditing]);
  useEffect(() => () => onEditing(null), [onEditing]);

  if (!isLatest) return null;
  if (!open) {
    return (
      <p className="propose-edit">
        <Button size="small" icon={PencilLine} onPress={() => setOpen(true)}>
          Propose an edit<span className="visually-hidden"> to {name}</span>
        </Button>
      </p>
    );
  }

  async function propose() {
    setBusy(true);
    setError(null);
    try {
      const proposed = await api.proposeEdit(projectId, version.document_id, {
        version: version.version,
        digest: digestOf(version.text),
        text: lineEnding ? text.replace(/\r?\n/g, lineEnding) : text,
      });
      setOpen(false);
      announce(
        `${name}: your version ${String(proposed.version)} is proposed. The project's owners approve or reject it.`,
      );
      onProposed();
    } catch (e) {
      if (e instanceof EscalationRefused && e.slug !== "not-permitted") await onStale(e.message);
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="propose-edit"
      aria-label="Propose an edit"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim() && text !== version.text) void propose();
      }}
    >
      <div className="field">
        <label htmlFor={`${id}-text`}>Your version of the text</label>
        <p className="hint" id={`${id}-hint`}>
          This becomes version {version.version + 1}, proposed as yours. The project&apos;s owners
          approve or reject it; version {version.version} stays as it was.
        </p>
        <textarea
          id={`${id}-text`}
          className="document-edit"
          aria-describedby={`${id}-hint`}
          required
          rows={12}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </div>
      <Button type="submit" size="small" variant="primary" isDisabled={busy || text === version.text}>
        Propose this version
      </Button>{" "}
      <Button
        size="small"
        variant="quiet"
        onPress={() => {
          setOpen(false);
          setText(version.text);
        }}
      >
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
