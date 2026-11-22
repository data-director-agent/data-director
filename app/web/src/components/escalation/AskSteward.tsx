/**
 * The one place an escalation is confirmed (docs/ui/steward-escalation-flows.md, flows A and B):
 * a note in the researcher's words, what will be shared, which they may narrow, and a plain
 * statement that the team may open the whole project while the request is open and that every
 * look is recorded and shown. Nothing is sent until they press **Send to a data steward**.
 *
 * With no steward team for the project it says so, and offers nothing to send (invariant 11).
 * With several teams and none chosen for the project, the researcher picks one. A step stopped
 * for a mandatory review stays stopped whatever is chosen, so its dialog offers **Leave it
 * stopped**, not **Not now**. A refusal is shown by what its slug means.
 */

import { Send } from "lucide-react";
import { useId, useState } from "react";

import {
  EscalationRefused,
  type NewEscalation,
  NOTE_MAX_LENGTH,
  type ProjectEscalations,
  SCOPE_LINE_MAX_LENGTH,
  SCOPE_MAX_LINES,
} from "../../project/escalations";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";
import { ModalDialog } from "../ui/Dialog";
import type { Offer } from "./StewardContext";
import { refusalSaid } from "./wording";

/** What is shared, line by line: the project, the conversation, and the matter itself. */
export function scopeOf(projectTitle: string | null, matter: readonly string[] = []): string[] {
  return [
    projectTitle ? `The project's title: ${projectTitle}` : "The project's title",
    "The recent conversation in this project and the runs in it",
    ...matter,
  ]
    .slice(0, SCOPE_MAX_LINES)
    .map((line) => line.slice(0, SCOPE_LINE_MAX_LENGTH));
}

export function AskSteward({
  offer,
  escalations,
  projectTitle,
  onSend,
  onClose,
}: {
  offer: Offer;
  /** The project's escalations as last read, with where a new one goes; undefined until read. */
  escalations: ProjectEscalations | undefined;
  projectTitle: string | null;
  onSend: (escalation: NewEscalation) => Promise<void>;
  onClose: () => void;
}) {
  const id = useId();
  const scope = scopeOf(projectTitle, offer.matter);
  const [note, setNote] = useState(offer.note ?? "");
  const [kept, setKept] = useState<boolean[]>(() => scope.map(() => true));
  const [team, setTeam] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unrouted = escalations?.unrouted ?? null;
  const routed = escalations?.teams.find((t) => t.team_id === (team ?? escalations.routes_to));
  const cannot = escalations === undefined || unrouted === "no-steward-team";

  async function send() {
    const missing = !note.trim() ? "note-required" : unrouted === "team-required" && team === null ? "team-required" : null;
    if (missing) {
      setError(refusalSaid(missing, ""));
      return;
    }
    setSending(true);
    setError(null);
    try {
      await onSend({
        note: note.trim(),
        origin: offer.origin,
        scope_shared: scope.filter((_, i) => kept[i]),
        ...(team === null ? {} : { team_id: team }),
      });
    } catch (e) {
      setError(e instanceof EscalationRefused ? refusalSaid(e.slug, e.message) : errorMessage(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <ModalDialog
      title="Ask a data steward"
      isOpen
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      footer={
        <>
          <Button onPress={onClose}>{offer.mandatory ? "Leave it stopped" : cannot ? "Close" : "Not now"}</Button>
          {!cannot && (
            <Button variant="primary" icon={Send} isPending={sending} onPress={() => void send()}>
              Send to a data steward
            </Button>
          )}
        </>
      }
    >
      {offer.mandatory && (
        <p className="callout status-warn">
          This step stays stopped until a data steward approves it, whatever you choose here.
        </p>
      )}
      {escalations === undefined ? (
        <p role="status">Finding who to send it to…</p>
      ) : unrouted === "no-steward-team" ? (
        <p>
          No data steward team is set up for this project, so this cannot be sent from here. Ask
          whoever runs Data Director for you who looks after research data at your institution.
        </p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <div className="field">
            <label htmlFor={`${id}-note`}>What would you like help with?</label>
            <textarea
              id={`${id}-note`}
              required
              rows={4}
              maxLength={NOTE_MAX_LENGTH}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
          {unrouted === "team-required" && (
            <fieldset className="field">
              <legend>Which data steward team?</legend>
              {escalations.teams.map((t) => (
                <div key={t.team_id} className="field-check">
                  <input
                    type="radio"
                    id={`${id}-team-${t.team_id}`}
                    name={`${id}-team`}
                    value={t.team_id}
                    checked={team === t.team_id}
                    onChange={() => setTeam(t.team_id)}
                  />
                  <label htmlFor={`${id}-team-${t.team_id}`}>
                    {t.supports.length > 0 ? `${t.name} (${t.supports.join(", ")})` : t.name}
                  </label>
                </div>
              ))}
            </fieldset>
          )}
          <fieldset className="field">
            <legend>What will be shared</legend>
            <p className="hint">
              Your note goes with it. Untick anything you would rather not point the steward to.
            </p>
            {scope.map((line, i) => (
              <div key={line} className="field-check">
                <input
                  type="checkbox"
                  id={`${id}-scope-${i}`}
                  checked={kept[i] ?? false}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setKept((was) => was.map((k, j) => (j === i ? checked : k)));
                  }}
                />
                <label htmlFor={`${id}-scope-${i}`}>{line}</label>
              </div>
            ))}
          </fieldset>
          <p>
            {routed ? `It goes to ${routed.name}. ` : ""}
            While your request is open, the team can open the whole project to help you. Every
            time a steward looks is recorded, and you can see it in the project.
            {routed?.response_time ? ` They usually answer within ${routed.response_time}.` : ""}
          </p>
        </form>
      )}
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
    </ModalDialog>
  );
}
