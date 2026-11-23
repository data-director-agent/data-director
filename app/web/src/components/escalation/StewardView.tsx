/**
 * A project opened by its data steward (docs/ui/steward-escalation-flows.md, flow C; #376): the
 * same pages the researcher has, under a banner that cannot be dismissed, "Viewing as a data
 * steward", which names whose project it is. Beside it are the requests routed to the steward's
 * team (the researcher's note, where it came from, its history and the steward's notes) with the
 * moves the harness lists for each (`StewardRequest`), and the steps the harness lets the steward
 * take in the project: write to the researchers, pause it, lift a pause, or ask an agent, which
 * opens the conversation page in the project, where each run acts for the steward (invariants 3,
 * 4 and 6).
 *
 * Each read is recorded by the server, once a day per steward; the researchers can see who looked.
 * Nothing renders for a member of the project.
 */

import "./Steward.css";

import { MessagesSquare, ShieldCheck } from "lucide-react";
import { useCallback } from "react";

import { useActiveProject } from "../../project/active";
import { LIVE_STATES, useEscalationsApi } from "../../project/escalations";
import { type StewardStep, asSteward, permits, stewardMay, useStewardApi } from "../../project/steward";
import { useProjectView } from "../../project/view";
import { Link, homePath, navigate } from "../../route";
import { useResource } from "../../useResource";
import { Button } from "../ui/Button";
import { type Noted, NotedAction } from "./NotedAction";
import { StewardRequest } from "./StewardRequest";

const STEP: Record<StewardStep, Noted> = {
  messages: { label: "Write to the researchers", field: "Your message", done: "Message sent to the researchers." },
  pause: {
    label: "Pause the project",
    field: "Why you are pausing it",
    done: "Project paused. Only advisers run until a steward on your team lifts the pause.",
  },
  resume: { label: "Lift the pause", field: "Why you are lifting it", done: "Pause lifted." },
};

export function StewardView({ projectId }: { projectId: string }) {
  const { view, reload: viewAgain } = useProjectView();
  const escalationsApi = useEscalationsApi();
  const api = useStewardApi();
  const { setProjectId } = useActiveProject();
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
            <StewardRequest
              key={e.escalation_id}
              projectId={projectId}
              escalation={e}
              stewarding={steps.latest}
              onDone={again}
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
        {stepsOpen(paused !== null).map(
          (step) =>
            permits(view, step === "messages" ? "message" : step) && (
              <NotedAction
                key={step}
                said={STEP[step]}
                send={(note) => api.step(projectId, step, note)}
                onDone={again}
              />
            ),
        )}
        {stewardMay(view, "run") && (
          <Button
            size="small"
            icon={MessagesSquare}
            onPress={() => {
              setProjectId(projectId);
              navigate(homePath({}));
            }}
          >
            Ask an agent in this project
          </Button>
        )}
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

/** The steps a steward may take with a note, by whether the project is paused. */
function stepsOpen(paused: boolean): StewardStep[] {
  return ["messages", paused ? "resume" : "pause"];
}
