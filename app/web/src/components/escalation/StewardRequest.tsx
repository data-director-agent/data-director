/**
 * One request in a project opened by its data steward (docs/ui/steward-escalation-flows.md,
 * flow C): its state, where it came from, the researcher's note, its history, and the moves the
 * harness lists for it.
 *
 * A request that came from a step the policy gate referred to a data steward also carries the
 * steward's decision on that step (docs/specs/stewardship.md, invariants 6 and 7): **Clear the
 * step** or **Refuse the step**, each with a reason, where the harness permits it; or, once
 * decided, the decision, by whom and when. Clearing is a policy exception, not approval: the
 * project's owners still approve what the step produces.
 */

import type { Escalation, ProjectStewarding } from "../../project/escalations";
import { stewardMay, useStewardApi } from "../../project/steward";
import { useProjectView } from "../../project/view";
import { formatDateTime } from "../../format";
import { Link, homePath } from "../../route";
import { MoveControls } from "./MoveControls";
import { type Noted, NotedAction } from "./NotedAction";
import { MOVE_SAID, originSaid, stewardStateSaid } from "./wording";

const WHEN = { dateStyle: "medium", timeStyle: "short" } as const;

const CLEAR: Noted = {
  label: "Clear the step",
  field: "Why you are clearing it",
  done: "Step cleared. The researchers still approve what it produces.",
};
const REFUSE: Noted = {
  label: "Refuse the step",
  field: "Why you are refusing it",
  done: "Step refused. The researchers can see your reason.",
};

export function StewardRequest({
  projectId,
  escalation,
  stewarding,
  onMove,
  onDone,
}: {
  projectId: string;
  escalation: Escalation;
  stewarding: ProjectStewarding | undefined;
  onMove: Parameters<typeof MoveControls>[0]["onMove"];
  /** Reads the project's requests and stewarding again, after a decision. */
  onDone: () => void;
}) {
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
              <time dateTime={h.at}>{formatDateTime(h.at, WHEN)}</time>: {h.by.name}{" "}
              {MOVE_SAID[h.move] ?? h.move}
              {h.note ? `: ${h.note}` : ""}
            </li>
          ))}
        </ol>
      </details>
      {escalation.origin.kind === "policy_gate" && escalation.origin.invocation_id && (
        <GateDecision
          projectId={projectId}
          invocationId={escalation.origin.invocation_id}
          stewarding={stewarding}
          onDone={onDone}
        />
      )}
      <MoveControls escalation={escalation} onMove={onMove} />
    </li>
  );
}

/** The steward's decision on a referred step: made, or the controls to make it. */
function GateDecision({
  projectId,
  invocationId,
  stewarding,
  onDone,
}: {
  projectId: string;
  invocationId: string;
  stewarding: ProjectStewarding | undefined;
  onDone: () => void;
}) {
  const api = useStewardApi();
  const { view } = useProjectView();
  const decided = stewarding?.gate_decisions.find((d) => d.invocation_id === invocationId);
  const run = (
    <Link to={homePath({ run: invocationId })}>
      Read the referred step<span className="visually-hidden"> {invocationId}</span>
    </Link>
  );
  if (decided) {
    return (
      <p className="steward-gate">
        <strong>{decided.verdict === "cleared" ? "Step cleared" : "Step refused"}</strong> by{" "}
        {decided.by.name} on <time dateTime={decided.at}>{formatDateTime(decided.at, WHEN)}</time>:{" "}
        {decided.reason}. {run}
      </p>
    );
  }
  const clears = stewardMay(view, "clear_gate");
  const refuses = stewardMay(view, "refuse_gate");
  if (!stewarding || (!clears && !refuses)) return <p className="steward-gate">{run}</p>;
  return (
    <div className="steward-gate">
      <p>
        A step that needs a data steward&apos;s approval stopped here. {run}. Clearing it does not
        yet restart it; the researcher runs it again.
      </p>
      <div className="steward-steps">
        {clears && (
          <NotedAction
            said={CLEAR}
            variant="primary"
            send={(note) => api.decideGate(projectId, invocationId, "cleared", note)}
            onDone={onDone}
          />
        )}
        {refuses && (
          <NotedAction
            said={REFUSE}
            send={(note) => api.decideGate(projectId, invocationId, "refused", note)}
            onDone={onDone}
          />
        )}
      </div>
    </div>
  );
}
