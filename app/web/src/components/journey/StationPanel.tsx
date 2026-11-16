/**
 * One stop of the journey map, opened: what the step is, its state and why, a link to what
 * produced it, the researcher's own marks, and a way to ask Data Director about it. Marking is
 * never a gate: any step may be marked done or skipped, or opened again, in any order.
 */

import { ArrowLeft, MessageSquare } from "lucide-react";
import { useEffect, useRef } from "react";

import { type Station, kindName, reasonText } from "../../flow/journey";
import type { Decision, StepMark } from "../../flow/types";
import { formatDate } from "../../format";
import { Link } from "../../route";
import { Button } from "../ui/Button";
import { STATE_WORDS } from "./JourneyMap";

export function StationPanel({
  station,
  projectId,
  decisions,
  onMark,
  onAsk,
  onClose,
  error,
}: {
  station: Station;
  projectId: string;
  decisions: Decision[];
  onMark(mark: StepMark): void;
  onAsk(): void;
  onClose(): void;
  error?: string | null;
}) {
  const { step, phase, state, reason } = station;
  const heading = useRef<HTMLHeadingElement>(null);
  // Opening a stop moves focus to it, so a keyboard or screen reader follows the press.
  useEffect(() => {
    heading.current?.focus();
  }, [step.id]);
  const project = `/projects/${encodeURIComponent(projectId)}`;
  return (
    <section className="station-panel" aria-labelledby="station-heading">
      <p className="station-panel-phase">
        Phase {phase.number}: {phase.name}
      </p>
      <h2 id="station-heading" tabIndex={-1} ref={heading}>
        {step.label}
      </h2>
      <p className="muted">{phase.summary}</p>
      <p>
        <strong>{step.out_of_scope ? "Not in this version" : STATE_WORDS[state]}</strong>
        {step.optional && " (optional)"}
        {station.suggested && " · Suggested next"}
        {station.waiting && " · Waiting on you"}
      </p>
      {reason && (
        <p>
          {reasonText(reason, decisions)}
          {reason.at && <span className="muted"> ({formatDate(reason.at)})</span>}
        </p>
      )}
      {reason?.document_id ? (
        <p>
          <Link to={`${project}?doc=${encodeURIComponent(reason.document_id)}`}>
            Open the {reason.document_kind ? kindName(reason.document_kind) : "document"}
          </Link>
        </p>
      ) : (
        reason?.source === "produced" && (
          <p>
            <Link to={project}>Open the project page</Link>
          </p>
        )
      )}
      {step.out_of_scope ? (
        <p>Data Director does not help with this step yet. You can still do it yourself.</p>
      ) : (
        <div className="station-panel-actions">
          {state === "done" || state === "skipped" ? (
            <Button size="small" onPress={() => onMark("open")}>
              Open again
            </Button>
          ) : (
            <>
              <Button size="small" onPress={() => onMark("done")}>
                Mark done
              </Button>
              <Button size="small" onPress={() => onMark("skipped")}>
                Skip
              </Button>
            </>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="callout status-danger">
          Data Director could not record that: {error}.
        </p>
      )}
      <div className="station-panel-actions">
        <Button variant="primary" icon={MessageSquare} onPress={onAsk}>
          Ask Data Director about this
        </Button>
        <Button variant="quiet" icon={ArrowLeft} onPress={onClose}>
          Back to the map
        </Button>
      </div>
    </section>
  );
}
