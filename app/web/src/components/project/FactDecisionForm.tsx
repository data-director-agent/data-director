/**
 * A person's decision on one project fact (docs/specs/projects.md, invariant 28). On an agent's
 * proposal they confirm it as it is, change it, or reject it; on a fact that stands, or one they
 * state themselves, they give its values. A reason is optional and kept with the decision; no
 * agent is given it.
 *
 * Whether sensitive data may be published, and the licence, are an owner's to decide: a member who
 * tries is told so, and nothing is recorded.
 */

import { Check, Pencil, X } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import { DecisionConflict } from "../../project/api";
import {
  type FactDecision,
  FactForbidden,
  type FactProposal,
  type FactVerdict,
  type ProjectFact,
  type ProjectFacts,
  cleaned,
  missingSlots,
  useFactsApi,
} from "../../project/facts";
import { Button } from "../ui/Button";
import { ReasonField, useDecisionError } from "./DecisionParts";
import { FactFields } from "./FactFields";
import { KIND_LABELS, describeFact } from "./factWording";

const REASON_MAX_LENGTH = 2000;
const OWNERS_ONLY =
  "Only an owner of this project may decide whether sensitive data is published, or the licence.";

function said(verdict: FactVerdict, fact: ProjectFact): string {
  if (verdict === "rejected")
    return `${KIND_LABELS[fact.fact_kind]}: proposal rejected.`;
  return `Recorded: ${describeFact(fact)}`;
}

/** A name for the form that differs between the forms on one panel. */
function legend(
  proposal: FactProposal | undefined,
  fact: ProjectFact,
  isNew: boolean,
): string {
  const kind = KIND_LABELS[fact.fact_kind].toLowerCase();
  const what =
    fact.fact_kind === "licence" ? kind : `${kind} ${fact.fact_subject}`;
  if (proposal) return `Your decision on the ${what}`;
  return isNew ? "New fact" : `Change the ${what}`;
}

export function FactDecisionForm({
  projectId,
  proposal,
  initial,
  isNew = false,
  onDecided,
  onStale,
  onCancel,
}: {
  projectId: string;
  /** The proposal decided on, or none for a fact that stands or one the person states. */
  proposal?: FactProposal;
  /** The fact as the form starts: the proposal's, the one that stands, or a blank one. */
  initial: ProjectFact;
  isNew?: boolean;
  onDecided: (value: ProjectFacts, said: string) => void;
  onStale: (detail: string) => Promise<void>;
  onCancel?: () => void;
}) {
  const api = useFactsApi();
  const id = useId();
  const [verdict, setVerdict] = useState<FactVerdict>(
    proposal ? "confirmed" : "changed",
  );
  const [fact, setFact] = useState<ProjectFact>(initial);
  const [reason, setReason] = useState("");
  const [sending, setSending] = useState(false);
  const { setError, alert } = useDecisionError();

  const choices: { value: FactVerdict; label: string }[] = [
    { value: "confirmed", label: "Confirm it as proposed" },
    { value: "changed", label: "Change it, then record my version" },
    { value: "rejected", label: "Reject it" },
  ];

  async function submit(event: FormEvent) {
    event.preventDefault();
    const sent = cleaned(fact);
    if (verdict === "changed") {
      const missing = missingSlots(sent);
      if (missing.length > 0 || !sent.fact_subject) {
        setError("Fill in every value marked required.");
        return;
      }
    }
    setSending(true);
    setError(null);
    const decision: FactDecision = {
      verdict,
      ...(proposal ? { proposal: proposal.proposal } : {}),
      ...(verdict === "changed" ? { fact: sent } : {}),
      ...(reason.trim() ? { reason } : {}),
    };
    try {
      const value = await api.decideFact(projectId, decision);
      setSending(false);
      onDecided(value, said(verdict, value.decided ?? sent));
    } catch (caught) {
      setSending(false);
      if (caught instanceof DecisionConflict) await onStale(caught.message);
      else if (caught instanceof FactForbidden) setError(OWNERS_ONLY);
      else setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  const submitLabel = {
    confirmed: "Confirm",
    changed: isNew ? "Record this fact" : "Record my version",
    rejected: "Reject",
  }[verdict];

  return (
    <form
      className="decision-form"
      onSubmit={submit}
      aria-labelledby={`${id}-legend`}
    >
      <fieldset className="field">
        <legend id={`${id}-legend`}>{legend(proposal, initial, isNew)}</legend>
        {proposal &&
          choices.map(({ value, label }) => (
            <div className="field-check" key={value}>
              <input
                type="radio"
                id={`${id}-${value}`}
                name={`${id}-verdict`}
                value={value}
                checked={verdict === value}
                onChange={() => setVerdict(value)}
              />
              <label htmlFor={`${id}-${value}`}>{label}</label>
            </div>
          ))}
      </fieldset>
      {verdict === "changed" && (
        <FactFields fact={fact} isNew={isNew} onChange={setFact} />
      )}
      <ReasonField
        id={id}
        label="Reason (optional)"
        hint="Kept with the decision, in the project's record, for your colleagues. No agent is given it."
        maxLength={REASON_MAX_LENGTH}
        rows={2}
        value={reason}
        onChange={setReason}
      />
      {alert}
      <p className="actions">
        <Button
          type="submit"
          variant="primary"
          icon={{ confirmed: Check, changed: Pencil, rejected: X }[verdict]}
          isDisabled={sending}
        >
          {sending ? "Recording…" : submitLabel}
        </Button>
        {onCancel && (
          <Button variant="quiet" onPress={onCancel}>
            Cancel
          </Button>
        )}
      </p>
    </form>
  );
}
