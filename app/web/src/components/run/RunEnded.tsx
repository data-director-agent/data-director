/**
 * What a streamed run came to when it did not finish (#69, #949): cancelled, failed with
 * `RUN_ERROR`, or interrupted, when the stream closed before the run ended. Each is said as it is
 * and no finish is invented for it. Focus moves to the heading when the screen appears, as it does
 * for a finished run's outcome.
 */

import "./Outcome.css";

import { useEffect, useRef } from "react";

import type { RunState } from "../../run/reduce";

type Ended = "cancelled" | "error" | "interrupted";

const ENDED: Record<Ended, { label: string; tone: string }> = {
  cancelled: { label: "Cancelled", tone: "warn" },
  error: { label: "Failed", tone: "danger" },
  interrupted: { label: "Interrupted", tone: "danger" },
};

export function isEndedUnfinished(phase: RunState["phase"]): phase is Ended {
  return phase === "cancelled" || phase === "error" || phase === "interrupted";
}

function Explanation({ run, phase }: { run: RunState; phase: Ended }) {
  switch (phase) {
    case "cancelled":
      return (
        <>
          <p>You cancelled this run before it finished. What it was still doing is not kept.</p>
          <p>Send your message again to start a new run.</p>
        </>
      );
    case "error":
      return (
        <div className="callout status-danger">
          <p className="problem-detail">{run.error ?? "The run gave no reason."}</p>
          <p>Send your message again, or ask a data steward if it fails again.</p>
        </div>
      );
    case "interrupted":
      return (
        <>
          <p>
            The connection to Data Director closed before the run ended, so this page does not know
            how it ended.
          </p>
          <p>
            Open this conversation again from Conversations to see what was stored before sending
            your message again.
          </p>
        </>
      );
  }
}

export function RunEnded({ run, idPrefix }: { run: RunState; idPrefix: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const { phase } = run;
  useEffect(() => {
    if (isEndedUnfinished(phase)) heading.current?.focus();
  }, [phase]);
  if (!isEndedUnfinished(phase)) return null;
  const { label, tone } = ENDED[phase];
  const headingId = `${idPrefix}-outcome`;
  return (
    <section className="outcome" aria-labelledby={headingId}>
      <h3 id={headingId} ref={heading} tabIndex={-1}>
        Outcome: <span className={`status status-${tone}`}>{label}</span>
      </h3>
      <Explanation run={run} phase={phase} />
    </section>
  );
}
