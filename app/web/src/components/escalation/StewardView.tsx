/**
 * A project opened by its data steward (docs/ui/steward-escalation-flows.md, flow C; #376): the
 * same pages the researcher has, under a banner that cannot be dismissed, "Viewing as a data
 * steward", which names whose project it is. Beside it are the requests routed to the steward's
 * team (the researcher's note, where it came from, its history and the steward's notes) with the
 * moves the harness lists for each, and the steps the harness lets the steward take in the
 * project: write to the researchers, pause it, or lift a pause (invariants 3, 4 and 6).
 *
 * Each read is recorded by the server, once a day per steward; the researchers can see who looked.
 * Nothing renders for a member of the project.
 */

import "./Steward.css";

import { ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";

import { type Escalation, LIVE_STATES, useEscalationsApi } from "../../project/escalations";
import { type StewardStep, asSteward, permits, useStewardApi } from "../../project/steward";
import { useProjectView } from "../../project/view";
import { formatDateTime } from "../../format";
import { errorMessage } from "../../run/api";
import { Link } from "../../route";
import { useResource } from "../../useResource";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";
import { MoveControls } from "./MoveControls";
import { NoteField } from "./NoteField";
import { MOVE_SAID, originSaid, stewardStateSaid } from "./wording";

export function StewardView({ projectId }: { projectId: string }) {
  const { view, reload: viewAgain } = useProjectView();
  const escalationsApi = useEscalationsApi();
  const api = useStewardApi();
  const steward = asSteward(view);
  const read = useResource(steward ? projectId : null, (id, signal) => escalationsApi.escalations(id, signal));
  const steps = useResource(steward ? projectId : null, (id, signal) => escalationsApi.stewarding(id, signal));
  const { reload: readAgain } = read;
  const { reload: stepsAgain } = steps;
  const again = useCallback(() => {
    readAgain();
    stepsAgain();
    viewAgain();
  }, [readAgain, stepsAgain, viewAgain]);
  if (!view || !steward) return null;

  const routed = (read.latest?.escalations ?? []).filter((e) => LIVE_STATES.includes(e.state));
  const paused = steps.latest?.paused ?? null;
  return (
    <section className="steward-view" aria-labelledby={`steward-view-${projectId}`}>
      <div className="callout status-warn steward-banner">
        <h2 id={`steward-view-${projectId}`}>
          <ShieldCheck size="1em" aria-hidden="true" /> Viewing as a data steward
        </h2>
        <p>
          This is {view.created_by.name}&apos;s project. You see it because a request is with your team. What you open here is recorded, and the
          researchers can see who looked. <Link to="/steward">Back to the requests</Link>
        </p>
        {paused && (
          <p>
            <strong>Paused by a data steward</strong>: {paused.reason}
          </p>
        )}
      </div>
      {routed.length > 0 && (
        <ul className="plain-list steward-requests" aria-label="Requests from this project">
          {routed.map((e) => (
            <Request
              key={e.escalation_id}
              escalation={e}
              onMove={async (move, note) => {
                try {
                  await api.move(projectId, e.escalation_id, move, note);
                } finally {
                  again();
                }
              }}
            />
          ))}
        </ul>
      )}
      <div className="steward-steps">
        {permits(view, "message") && <Step projectId={projectId} step="messages" onDone={again} />}
        {!paused && permits(view, "pause") && <Step projectId={projectId} step="pause" onDone={again} />}
        {paused && permits(view, "resume") && <Step projectId={projectId} step="resume" onDone={again} />}
      </div>
      {!permits(view, "message") && (
        <p className="hint">
          You can write to the researchers or pause the project only while a request from it is with
          your team.
        </p>
      )}
    </section>
  );
}

function Request({ escalation, onMove }: { escalation: Escalation; onMove: Parameters<typeof MoveControls>[0]["onMove"] }) {
  return (
    <li className="callout">
      <p>
        <strong>{stewardStateSaid(escalation.state)}</strong>
        <span className="hint">
          {" "}
          · {originSaid(escalation.origin.kind)} · to {escalation.team_name}
          {escalation.taken_by ? ` · taken by ${escalation.taken_by.name}` : ""}
        </span>
      </p>
      <p>{escalation.note}</p>
      <details>
        <summary>History</summary>
        <ol className="steward-history">
          {escalation.history.map((h, index) => (
            <li key={`${h.move}-${String(index)}`}>
              <time dateTime={h.at}>{formatDateTime(h.at, { dateStyle: "medium", timeStyle: "short" })}</time>:{" "}
              {h.by.name} {MOVE_SAID[h.move] ?? h.move}
              {h.note ? `: ${h.note}` : ""}
            </li>
          ))}
        </ol>
      </details>
      <MoveControls escalation={escalation} onMove={onMove} />
    </li>
  );
}

const STEP: Record<StewardStep, { label: string; field: string; done: string }> = {
  messages: { label: "Write to the researchers", field: "Your message", done: "Message sent to the researchers." },
  pause: {
    label: "Pause the project",
    field: "Why you are pausing it",
    done: "Project paused. Only advisers run until a steward on your team lifts the pause.",
  },
  resume: { label: "Lift the pause", field: "Why you are lifting it", done: "Pause lifted." },
};

function Step({ projectId, step, onDone }: { projectId: string; step: StewardStep; onDone: () => void }) {
  const api = useStewardApi();
  const announce = useAnnounce();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const said = STEP[step];
  if (!open) {
    return (
      <Button size="small" onPress={() => setOpen(true)}>
        {said.label}
      </Button>
    );
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!note.trim()) return;
        setBusy(true);
        setError(null);
        api.step(projectId, step, note.trim()).then(
          () => {
            setOpen(false);
            setNote("");
            announce(said.done);
            onDone();
          },
          (e: unknown) => setError(errorMessage(e)),
        ).finally(() => setBusy(false));
      }}
    >
      <NoteField label={said.field} value={note} onChange={setNote} />
      <Button type="submit" size="small" variant="primary" isPending={busy}>
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
