/**
 * One document: its latest version's state and text, the form to decide on it while it is
 * undecided, and its earlier versions.
 *
 * The text is shown as it is stored, not rendered, because that is the text a decision names by
 * its digest and the text the deposit package will hold. Whether a reason is required comes from
 * the harness's rule (`ReviewRules`): a departure from the draft needs one, a plain approval does
 * not, so that approving what is right asks for nothing more (`docs/ui/best-practices.md`, 8).
 *
 * After a decision, focus moves to the document's heading, since the form it was in has gone. A
 * decision the server refused because the document has moved on is said in an alert, which takes
 * the focus, above the latest version, which the page has read again.
 */

import { Check, Pencil, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { RunRefused } from "../../run/api";
import {
  DecisionConflict,
  type DecisionRequest,
  type DocumentVersion,
  type ProjectDocument,
  type ProjectDocuments,
  type ReviewRules,
  digestOf,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";

const KINDS: Record<string, string> = {
  metadata_record: "Metadata record",
  readme: "README",
  data_dictionary: "Data dictionary",
  dmp: "Data management plan",
};

const STATES = {
  proposed: { label: "Proposed, not reviewed", className: "status-warn" },
  approved: { label: "Approved", className: "status-ok" },
  rejected: { label: "Rejected", className: "status-danger" },
} as const;

type Choice = "approve" | "edit" | "reject";

export function documentName(document: Pick<ProjectDocument, "document_kind" | "document_title">) {
  return document.document_title ?? KINDS[document.document_kind] ?? "Document";
}

function When({ at }: { at: string }) {
  const shown = new Date(at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  return <time dateTime={at}>{shown}</time>;
}

function Provenance({ version }: { version: DocumentVersion }) {
  const by = version.drafted_by;
  return (
    <>
      {by ? (
        <>
          Drafted by{" "}
          <code>
            {by.agent_id}@{by.agent_version}
          </code>
        </>
      ) : (
        <>Edited by {version.added_by.name}</>
      )}
      {" on "}
      <When at={version.added_at} />
    </>
  );
}

function State({ version }: { version: DocumentVersion }) {
  const { label, className } = STATES[version.state];
  const decision = version.decision;
  return (
    <>
      <span className={`status ${className}`}>{label}</span>
      {decision && (
        <>
          {" "}
          by {decision.decided_by.name} on <When at={decision.decided_at} />
        </>
      )}
    </>
  );
}

export function DocumentReview({
  projectId,
  document,
  rules,
  onDecided,
  onStale,
}: {
  projectId: string;
  document: ProjectDocument;
  rules: ReviewRules;
  onDecided: (value: ProjectDocuments, said: string) => void;
  onStale: () => Promise<void>;
}) {
  const latest = document.versions[document.versions.length - 1];
  const earlier = document.versions.slice(0, -1).reverse();
  const name = documentName(document);
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const alert = useRef<HTMLDivElement>(null);
  const [stale, setStale] = useState<string | null>(null);

  useEffect(() => {
    if (stale) alert.current?.focus();
  }, [stale]);

  if (!latest) return null;

  const decided = (value: ProjectDocuments, said: string) => {
    setStale(null);
    onDecided(value, said);
    heading.current?.focus();
  };

  const refused = async (detail: string) => {
    await onStale();
    setStale(detail);
  };

  return (
    <article className="document-review" aria-labelledby={headingId}>
      <h2 id={headingId} ref={heading} tabIndex={-1}>
        {name}
      </h2>
      <p>
        Version {latest.version}: <State version={latest} />
      </p>
      <p className="hint">
        <Provenance version={latest} />. <code>{latest.media_type}</code>
        {latest.conforms_to && (
          <>
            , following <code>{latest.conforms_to}</code>
          </>
        )}
        .
      </p>
      {latest.decision?.reason && (
        <p>
          <strong>Reason:</strong> {latest.decision.reason}
        </p>
      )}
      {stale && (
        <div role="alert" className="callout status-warn" ref={alert} tabIndex={-1}>
          <p>
            Your decision was not recorded: {stale} The latest version is shown below. Read it,
            then decide again.
          </p>
        </div>
      )}
      <h3>Text of version {latest.version}</h3>
      <pre className="json-view document-text">{latest.text}</pre>
      {latest.state === "proposed" && (
        <DecisionForm
          key={`${latest.document_id}:${latest.version}`}
          projectId={projectId}
          name={name}
          version={latest}
          rules={rules}
          onDecided={decided}
          onStale={refused}
        />
      )}
      {earlier.length > 0 && (
        <details className="document-history">
          <summary>Earlier versions ({earlier.length})</summary>
          <ol reversed>
            {earlier.map((version) => (
              <li key={version.version}>
                Version {version.version}: <State version={version} />. <Provenance version={version} />.
                {version.decision?.reason && <> Reason: {version.decision.reason}</>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  );
}

function DecisionForm({
  projectId,
  name,
  version,
  rules,
  onDecided,
  onStale,
}: {
  projectId: string;
  name: string;
  version: DocumentVersion;
  rules: ReviewRules;
  onDecided: (value: ProjectDocuments, said: string) => void;
  onStale: (detail: string) => Promise<void>;
}) {
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
        ...(choice === "edit" ? { edited_text: edited } : {}),
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
            This becomes version {n + 1}, and is approved as you write it here. Version {n} stays
            as it was.
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
