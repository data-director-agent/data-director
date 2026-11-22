/**
 * The decision on a document's latest version while it is undecided: approve it as it is, edit
 * it and approve the person's version, or reject it. Whether a reason is required comes from the
 * harness's rule (`ReviewRules`): a departure from the draft needs one, a plain approval does not,
 * so that approving what is right asks for nothing more (`docs/ui/best-practices.md`, 8).
 *
 * No decision is chosen until the person chooses one, so that approving is never the default, and
 * the form says how many gaps and open questions the version has beside the button that records
 * it. Approving a version with any gap as it is asks again, naming the count (#1282).
 *
 * While the person edits, `onEditing` is given their text, so that the reader's preview can show
 * their version; it is given null when they choose otherwise.
 */

import { Check, Pencil, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useState } from "react";

import {
  DecisionConflict,
  type DecisionRequest,
  type DocumentVersion,
  type ProjectDocuments,
  type ReviewRules,
  digestOf,
  useProjectApi,
} from "../../project/api";
import { type VersionGaps, gapSentence } from "../../project/gaps";
import { RunRefused } from "../../run/api";
import { Button } from "../ui/Button";
import { ApproveWithGaps } from "./ApproveWithGaps";
import { ReasonField, useDecisionError } from "./DecisionParts";

type Choice = "approve" | "edit" | "reject";

export function DecisionForm({
  projectId,
  name,
  version,
  gaps,
  rules,
  onDecided,
  onStale,
  onEditing,
}: {
  projectId: string;
  name: string;
  version: DocumentVersion;
  /** What the version leaves open, which approving it as it is keeps. */
  gaps: VersionGaps;
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
  const [choice, setChoice] = useState<Choice | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [edited, setEdited] = useState(version.text);
  const [sending, setSending] = useState(false);
  const { setError, alert } = useDecisionError();

  useEffect(() => {
    onEditing(choice === "edit" ? edited : null);
  }, [choice, edited, onEditing]);

  // The preview goes back to the stored text when the form goes.
  useEffect(() => () => onEditing(null), [onEditing]);

  const required =
    choice !== null &&
    {
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
    none: "Rejecting, or editing before approving, needs one.",
  }[choice ?? "none"];
  const submitLabel = {
    approve: `Approve version ${n}`,
    edit: "Approve my edited version",
    reject: `Reject version ${n}`,
    none: "Record my decision",
  }[choice ?? "none"];

  function submit(event: FormEvent) {
    event.preventDefault();
    // The browser stops a form with no choice; this keeps the type narrow.
    if (choice === null) return;
    if (choice === "approve" && gaps.gaps > 0) setConfirming(true);
    else void record(choice);
  }

  async function record(chosen: Choice) {
    setConfirming(false);
    setSending(true);
    setError(null);
    try {
      const request: DecisionRequest = {
        version: n,
        // The text this page showed, as it showed it.
        digest: digestOf(version.text),
        decision: chosen === "reject" ? "rejected" : "approved",
        ...(reason.trim() ? { reason } : {}),
        ...(chosen === "edit"
          ? {
              edited_text: lineEnding
                ? edited.replace(/\r?\n/g, lineEnding)
                : edited,
            }
          : {}),
      };
      const value = await api.decide(projectId, version.document_id, request);
      const said = {
        approve: `${name}: version ${n} approved.`,
        edit: `${name}: your edited version ${value.decided?.version ?? n + 1} approved.`,
        reject: `${name}: version ${n} rejected.`,
      }[chosen];
      onDecided(value, said);
    } catch (caught) {
      setSending(false);
      if (caught instanceof DecisionConflict) await onStale(caught.message);
      else if (caught instanceof RunRefused) setError(caught.message);
      else setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  return (
    <form
      className="decision-form"
      onSubmit={submit}
      aria-labelledby={`${id}-legend`}
    >
      <fieldset className="field">
        <legend id={`${id}-legend`}>Your decision on version {n}</legend>
        {choices.map(({ value, label }) => (
          <div className="field-check" key={value}>
            <input
              type="radio"
              id={`${id}-${value}`}
              name={`${id}-choice`}
              value={value}
              required
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
            This becomes version {n + 1}, and is approved as you write it here.
            Version {n} stays as it was.
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
      <ReasonField
        id={id}
        label={`Reason ${required ? "(required)" : "(optional)"}`}
        hint={`${hint} It is kept with the decision, in the project's record.`}
        required={required}
        maxLength={rules.reason_max_length}
        rows={3}
        value={reason}
        onChange={setReason}
      />
      <p id={`${id}-gaps`} className={gaps.gaps > 0 ? "callout status-warn" : "hint"}>
        {gapSentence(gaps, n)}
      </p>
      {alert}
      {/* Not `isPending`: the form is gone once the decision is recorded, and the button's busy
          indicator would be left behind without its label (as in `Account.tsx`). Focus goes to
          the heading, or to the alert, so disabling the button does not lose it. */}
      <Button
        type="submit"
        variant="primary"
        icon={choice ? { approve: Check, edit: Pencil, reject: X }[choice] : undefined}
        aria-describedby={`${id}-gaps`}
        isDisabled={sending}
      >
        {sending ? "Recording…" : submitLabel}
      </Button>
      <ApproveWithGaps
        version={n}
        gaps={gaps}
        isOpen={confirming}
        onCancel={() => setConfirming(false)}
        onApprove={() => void record("approve")}
      />
    </form>
  );
}
