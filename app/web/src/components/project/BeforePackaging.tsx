/**
 * What a person decides and confirms before a deposit package is built (docs/specs/deposit.md,
 * "The pause before packaging"; Blueprint C2).
 *
 * The harness lists each file the inventory's names or its personal-data findings mark, with what
 * to check, in its own words; the person decides each one and confirms the checks before deposit.
 * Each decision and the confirmation are recorded for the person signed in. No item is never
 * clearance: what was not checked is always said.
 */

import { Check, ShieldCheck } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import {
  type DepositReview,
  type ItemDecision,
  type ReviewItem,
  useProjectApi,
} from "../../project/api";
import { formatDate } from "../../format";
import { Button } from "../ui/Button";

const DECISIONS: { value: ItemDecision; label: string; done: string }[] = [
  { value: "keep", label: "I checked it: deposit it as it is", done: "Checked: deposited as it is" },
  { value: "leave_out", label: "Leave it out of the deposit", done: "Left out of the deposit" },
  {
    value: "change",
    label: "Deposit a changed copy, such as a redacted or generalised one",
    done: "A changed copy is deposited",
  },
];

function decidedText(item: ReviewItem): string | null {
  const made = item.decision;
  if (!made) return null;
  const words = DECISIONS.find((d) => d.value === made.decision)?.done ?? made.decision;
  const note = made.note ? ` (${made.note})` : "";
  return `${words}${note}. Decided by ${made.decided_by.name}, ${formatDate(made.decided_at)}.`;
}

/** A form's submit handler that runs `action` and says whether it is still sending. */
function useSubmit(action: () => Promise<void>) {
  const [sending, setSending] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    try {
      await action();
    } finally {
      setSending(false);
    }
  };
  return { sending, submit };
}

function ItemForm({
  item,
  onDecide,
}: {
  item: ReviewItem;
  onDecide: (decision: ItemDecision, note: string) => Promise<void>;
}) {
  const id = useId();
  const [decision, setDecision] = useState<ItemDecision | null>(item.decision?.decision ?? null);
  const [note, setNote] = useState("");
  const where = item.column ? `${item.path}, column ${item.column}` : item.path;
  const { sending, submit } = useSubmit(async () => {
    if (decision) await onDecide(decision, note);
  });

  return (
    <form className="decision-form" onSubmit={submit} aria-labelledby={`${id}-legend`}>
      <fieldset className="field">
        <legend id={`${id}-legend`}>
          <code>{where}</code>: {item.kind.replaceAll("_", " ")}
        </legend>
        <p>{item.question}</p>
        {item.decision && <p className="hint">{decidedText(item)}</p>}
        {DECISIONS.map(({ value, label }) => (
          <div className="field-check" key={value}>
            <input
              type="radio"
              id={`${id}-${value}`}
              name={`${id}-decision`}
              value={value}
              checked={decision === value}
              onChange={() => setDecision(value)}
            />
            <label htmlFor={`${id}-${value}`}>{label}</label>
          </div>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor={`${id}-note`}>Note (optional)</label>
        <input id={`${id}-note`} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
      </div>
      <Button type="submit" icon={Check} isPending={sending} isDisabled={!decision}>
        {item.decision ? "Record my new decision" : "Record my decision"}
      </Button>
    </form>
  );
}

function Confirmation({
  review,
  onConfirm,
}: {
  review: DepositReview;
  onConfirm: (confirmed: string[]) => Promise<void>;
}) {
  const id = useId();
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const { sending, submit } = useSubmit(() => onConfirm([...ticked]));
  const made = review.confirmation;
  if (made) {
    return (
      <div className="callout status-ok">
        <p>
          Confirmed by {made.confirmed_by.name}, {formatDate(made.confirmed_at)}:
        </p>
        <ul>
          {made.statements.map((s) => (
            <li key={s.id}>{s.text}</li>
          ))}
        </ul>
      </div>
    );
  }
  const all = review.statements.every((s) => ticked.has(s.id));
  const toggle = (statement: string) => {
    const next = new Set(ticked);
    if (next.has(statement)) next.delete(statement);
    else next.add(statement);
    setTicked(next);
  };
  return (
    <form className="decision-form" onSubmit={submit} aria-labelledby={`${id}-legend`}>
      <fieldset className="field">
        <legend id={`${id}-legend`}>Before deposit, I confirm that:</legend>
        {review.statements.map((s) => (
          <div className="field-check" key={s.id}>
            <input
              type="checkbox"
              id={`${id}-${s.id}`}
              checked={ticked.has(s.id)}
              onChange={() => toggle(s.id)}
            />
            <label htmlFor={`${id}-${s.id}`}>{s.text}</label>
          </div>
        ))}
      </fieldset>
      <Button type="submit" icon={ShieldCheck} isPending={sending} isDisabled={!all}>
        Confirm
      </Button>
    </form>
  );
}

/** The items to decide, what was not checked, and the confirmation. `onChanged` is called after
 * each decision or confirmation is recorded, so the panel can check the project again. */
export function BeforePackaging({
  projectId,
  review,
  onChanged,
}: {
  projectId: string;
  review: DepositReview;
  onChanged: () => void;
}) {
  const api = useProjectApi();
  const [failed, setFailed] = useState<string | null>(null);

  const record = async (send: () => Promise<DepositReview>) => {
    setFailed(null);
    try {
      await send();
      onChanged();
    } catch (error: unknown) {
      setFailed(error instanceof Error ? error.message : String(error));
    }
  };

  const open = review.items.filter((i) => !i.decision).length;
  return (
    <section className="deposit-review" aria-labelledby="deposit-decide">
      <h3 id="deposit-decide">Decide before packaging</h3>
      {review.items.length > 0 ? (
        <p className="hint">
          Data Director marked these files from their names and from what the inventory command
          found. Each is a prompt for you, not a finding: decide each one ({open} of{" "}
          {review.items.length} still to decide). Data Director does not change your files.
        </p>
      ) : (
        <p className="hint">Nothing in what was checked was marked for you to decide.</p>
      )}
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not record that: {failed}</p>
        </div>
      )}
      {review.items.map((item) => (
        <ItemForm
          key={item.item_id}
          item={item}
          onDecide={(decision, note) =>
            record(() => api.decideItem(projectId, item.item_id, decision, note.trim() || undefined))
          }
        />
      ))}
      <h4>What was not checked</h4>
      <ul>
        {review.not_checked.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
      <Confirmation
        review={review}
        onConfirm={(confirmed) => record(() => api.confirmChecks(projectId, confirmed))}
      />
    </section>
  );
}
