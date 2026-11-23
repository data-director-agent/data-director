/**
 * The project pane's part on data stewards (docs/ui/steward-escalation-flows.md, flow A): the
 * **Ask a data steward** control, reachable by keyboard on every page that shows the pane; each
 * request with its one status line and the moves the researcher may make; and a steward's pause,
 * with who can lift it. Withdrawing needs no note and leaves a pause in place (invariant 8);
 * replying and re-opening need one. With no steward team, the control says so (invariant 11).
 */

import { LifeBuoy, Undo2 } from "lucide-react";
import { useState } from "react";

import type { Escalation, ResearcherMove } from "../../project/escalations";
import { movesPermitted } from "../../project/steward";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";
import { NoteField } from "./NoteField";
import { useSteward } from "./StewardContext";
import { StewardRecord } from "./StewardRecord";
import { stateSaid, statusLine } from "./wording";

export function StewardSection() {
  const steward = useSteward();
  if (!steward) return null;
  const read = steward.escalations;
  const shown = (read?.escalations ?? []).filter((e) => e.state !== "withdrawn");
  const paused = steward.stewarding?.paused ?? null;
  return (
    <section aria-labelledby="steward-heading" className="pane-section">
      <h3 id="steward-heading">Data steward</h3>
      {paused && (
        <p className="callout status-warn">
          A data steward paused this project on the steward team's behalf: {paused.reason}. Only
          advisers run until a steward on that team lifts the pause, even if you withdraw a request.
        </p>
      )}
      {shown.length > 0 && (
        <ul className="plain-list" aria-label="Requests to a data steward">
          {shown.map((e) => (
            <EscalationRow key={e.escalation_id} escalation={e} />
          ))}
        </ul>
      )}
      <AskStewardControl />
      <StewardRecord stewarding={steward.stewarding} />
    </section>
  );
}

/** The **Ask a data steward** control, or, with no steward team for the project, why there is none. */
export function AskStewardControl() {
  const steward = useSteward();
  if (!steward) return null;
  const read = steward.escalations;
  if (read?.unrouted === "no-steward-team") {
    return (
      <p className="hint">
        No data steward team is set up for this project. Ask whoever runs Data Director for you who
        looks after research data at your institution.
      </p>
    );
  }
  return (
    <Button size="small" icon={LifeBuoy} isDisabled={!read} onPress={() => steward.offer({ origin: { kind: "researcher" } })}>
      Ask a data steward
    </Button>
  );
}

const NEEDS_NOTE: Partial<Record<ResearcherMove, { label: string; field: string }>> = {
  reply: { label: "Reply", field: "Your reply to the data steward" },
  reopen: { label: "Re-open", field: "Why you are re-opening it" },
};

/** The moves the harness lets the researcher make on `escalation`. */
function movesOf(escalation: Escalation): ResearcherMove[] {
  return movesPermitted(escalation).filter((m): m is ResearcherMove =>
    ["reply", "withdraw", "reopen"].includes(m),
  );
}

function EscalationRow({ escalation }: { escalation: Escalation }) {
  const steward = useSteward();
  const announce = useAnnounce();
  const [writing, setWriting] = useState<ResearcherMove | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!steward) return null;

  async function make(move: ResearcherMove) {
    if (!steward) return;
    setBusy(true);
    setError(null);
    try {
      await steward.move(escalation, move, NEEDS_NOTE[move] ? note.trim() : undefined);
      setWriting(null);
      setNote("");
      announce(move === "withdraw" ? "Request withdrawn." : move === "reply" ? "Reply sent." : "Request re-opened.");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const asked = writing ? NEEDS_NOTE[writing] : undefined;
  return (
    <li className="callout">
      <p>
        <strong>{stateSaid(escalation.state)}</strong>
      </p>
      <p className="hint">{statusLine(escalation)}</p>
      <p>{escalation.note}</p>
      {writing && asked ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (note.trim()) void make(writing);
          }}
        >
          <NoteField label={asked.field} value={note} onChange={setNote} />
          <Button type="submit" size="small" variant="primary" isPending={busy}>
            {asked.label}
          </Button>{" "}
          <Button size="small" variant="quiet" onPress={() => setWriting(null)}>
            Cancel
          </Button>
        </form>
      ) : (
        <p>
          {movesOf(escalation).map((move) =>
            NEEDS_NOTE[move] ? (
              <Button key={move} size="small" onPress={() => setWriting(move)}>
                {NEEDS_NOTE[move].label}
              </Button>
            ) : (
              <Button key={move} size="small" variant="quiet" icon={Undo2} isPending={busy} onPress={() => void make(move)}>
                Withdraw<span className="visually-hidden"> this request</span>
              </Button>
            ),
          )}
        </p>
      )}
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
    </li>
  );
}
