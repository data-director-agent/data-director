/**
 * The decision on a document's latest version while it is undecided: approve it as it is, edit
 * it and approve the person's version, or reject it. Whether a reason is required comes from the
 * harness's rule (`ReviewRules`): a departure from the draft needs one, a plain approval does not,
 * so that approving what is right asks for nothing more (`docs/ui/best-practices.md`, 8).
 *
 * While the person edits, `onEditing` is given their text, so that the reader's preview can show
 * their version; it is given null when they choose otherwise.
 */

import { Check, Pencil, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import {
  DecisionConflict,
  type DecisionRequest,
  type DocumentVersion,
  type ProjectDocuments,
  type ReviewRules,
  digestOf,
  useProjectApi,
} from "../../project/api";
import { RunRefused } from "../../run/api";
import { Button } from "../ui/Button";

type Choice = "approve" | "edit" | "reject";

export function DecisionForm({
  projectId,
  name,
  version,
  rules,
  onDecided,
  onStale,
  onEditing,
}: {
  projectId: string;
  name: string;
  version: DocumentVersion;
  rules: ReviewRules;
  onDecided: (value: ProjectDocuments, said: string) => void;
  onStale: (detail: string) => Promise<void>;
  onEditing: (text: string | null) => void;
}) {
  // A textarea gives back its text with LF line endings whatever it was given, so a document
  // stored with CRLF gets them back, and the person's version differs only where they edited it.
  const lineEnding = version.text.includes("\r\n") ? "\r\n" : null;
  const api = useProjectApi();
  const id = useId();
  const [choice, setChoice] = useState<Choice>("approve");
  const [reason, setReason] = useState("");
  const [edited, setEdited] = useState(version.text);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    onEditing(choice === "edit" ? edited : null);
  }, [choice, edited, onEditing]);

  // The preview goes back to the stored text when the form goes.
  useEffect(() => () => onEditing(null), [onEditing]);

  const required = {
    approve: rules.reason_required.approved,
    edit: rules.reason_required.edited_and_approved,
    reject: rules.reason_required.rejected,
  }[choice];
  const n = version.version;
  const choices: { value: Choice; label: string }[] = [
    { value: "approve", label: `Approve version ${n} as it is` },
    { value: "edit", label: "Edit it, then approve my version" },
    { value: "reject", label: `Reject version ${n}` },
  ];
  const hint = {
    approve: "Anything a colleague should know about this approval.",
    edit: "Say what you changed and why.",
    reject: "Say what is wrong, so that the next draft can put it right.",
  }[choice];
  const submitLabel = {
    approve: `Approve version ${n}`,
    edit: "Approve my edited version",
    reject: `Reject version ${n}`,
  }[choice];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(null);
    try {
      const request: DecisionRequest = {
        version: n,
        // The text this page showed, as it showed it.
        digest: digestOf(version.text),
        decision: choice === "reject" ? "rejected" : "approved",
        ...(reason.trim() ? { reason } : {}),
        ...(choice === "edit"
          ? {
              edited_text: lineEnding ? edited.replace(/\r?\n/g, lineEnding) : edited,
            }
          : {}),
      };
      const value = await api.decide(projectId, version.document_id, request);
      const said = {
        approve: `${name}: version ${n} approved.`,
        edit: `${name}: your edited version ${value.decided?.version ?? n + 1} approved.`,
        reject: `${name}: version ${n} rejected.`,
      }[choice];
      onDecided(value, said);
    } catch (caught) {
      setSending(false);
      if (caught instanceof DecisionConflict) await onStale(caught.message);
      else if (caught instanceof RunRefused) setError(caught.message);
      else setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  return (
    <form className="decision-form" onSubmit={submit} aria-labelledby={`${id}-legend`}>
      <fieldset className="field">
        <legend id={`${id}-legend`}>Your decision on version {n}</legend>
        {choices.map(({ value, label }) => (
          <div className="field-check" key={value}>
            <input
              type="radio"
              id={`${id}-${value}`}
              name={`${id}-choice`}
              value={value}
              checked={choice === value}
              onChange={() => setChoice(value)}
            />
            <label htmlFor={`${id}-${value}`}>{label}</label>
          </div>
        ))}
      </fieldset>
      {choice === "edit" && (
        <div className="field">
          <label htmlFor={`${id}-edited`}>Your version of the text</label>
          <p className="hint" id={`${id}-edited-hint`}>
            This becomes version {n + 1}, and is approved as you write it here. Version {n} stays as
            it was.
          </p>
          <textarea
            id={`${id}-edited`}
            className="document-edit"
            aria-describedby={`${id}-edited-hint`}
            required
            rows={12}
            value={edited}
            onChange={(event) => setEdited(event.target.value)}
          />
        </div>
      )}
      <div className="field">
        <label htmlFor={`${id}-reason`}>Reason {required ? "(required)" : "(optional)"}</label>
        <p className="hint" id={`${id}-reason-hint`}>
          {hint} It is kept with the decision, in the project's record.
        </p>
        <textarea
          id={`${id}-reason`}
          aria-describedby={`${id}-reason-hint`}
          required={required}
          maxLength={rules.reason_max_length}
          rows={3}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      {error && (
        <div role="alert" className="callout status-danger" ref={errorRef} tabIndex={-1}>
          <p>The decision was not recorded: {error}</p>
        </div>
      )}
      {/* Not `isPending`: the form is gone once the decision is recorded, and the button's busy
          indicator would be left behind without its label (as in `Account.tsx`). Focus goes to
          the heading, or to the alert, so disabling the button does not lose it. */}
      <Button
        type="submit"
        variant="primary"
        icon={{ approve: Check, edit: Pencil, reject: X }[choice]}
        isDisabled={sending}
      >
        {sending ? "Recording…" : submitLabel}
      </Button>
    </form>
  );
}
