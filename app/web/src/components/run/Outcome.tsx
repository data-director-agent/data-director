/**
 * What a run came to, routed on the envelope's outcome status (checklist items 4 and 5).
 *
 * Succeeded shows the result and the evidence it rests on. Abstained and referred are answers in
 * their own right, each with what it means and what to do next, not errors. Failed shows the
 * problem as the harness stated it. Human review of proposed changes, and resuming a suspended
 * run, are not built yet, and are drawn in place (#72, #73).
 */

import { type Ref, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { OUTCOME, REASON } from "../../manifest/wording";
import { problemSlug } from "../../run/stages";
import type { RunResult } from "../../run/types";
import { NotBuilt } from "../NotBuilt";
import { EvidencePanel } from "./EvidencePanel";
import { ResultView } from "./ResultView";

function RunId({ id }: { id: string }) {
  const [copied, setCopied] = useState<string | null>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied("Copied the run id.");
    } catch {
      setCopied("Could not copy; select the run id instead.");
    }
  }
  return (
    <p>
      Run id: <code className="run-id">{id}</code>{" "}
      <button type="button" onClick={() => void copy()}>
        Copy run id
      </button>{" "}
      <span role="status">{copied}</span>
    </p>
  );
}

function Reason({ code }: { code: string | null | undefined }) {
  if (!code) return null;
  const reason = REASON[code];
  return (
    <dl className="facts">
      <dt>Why</dt>
      <dd>
        {reason ? reason.meaning : "No explanation is recorded for this reason."}{" "}
        <span className="muted">
          (<code>{code}</code>)
        </span>
      </dd>
      {reason && (
        <>
          <dt>What to do next</dt>
          <dd>{reason.next}</dd>
        </>
      )}
    </dl>
  );
}

export function Outcome({
  result,
  agent,
  idPrefix,
  headingRef,
  onEditInput,
}: {
  result: RunResult;
  agent: AgentView;
  idPrefix: string;
  headingRef?: Ref<HTMLHeadingElement>;
  onEditInput?: () => void;
}) {
  const { envelope, checks } = result;
  const { outcome } = envelope;
  const { label, tone } = OUTCOME[outcome.status];
  const headingId = `${idPrefix}-outcome`;
  const evidence = envelope.evidence ?? [];
  const slug = problemSlug(envelope.problem?.type);
  const editButton = onEditInput && (
    <p>
      <button type="button" onClick={onEditInput}>
        Edit the input and run again
      </button>
    </p>
  );

  return (
    <section className="outcome" aria-labelledby={headingId}>
      <h3 id={headingId} ref={headingRef} tabIndex={-1}>
        Outcome: <span className={`status status-${tone}`}>{label}</span>
      </h3>
      <p>{outcome.statement}</p>

      {outcome.status === "abstained" && (
        <div className="callout status-warn">
          <Reason code={outcome.reason_code} />
          {editButton}
        </div>
      )}

      {outcome.status === "referred" && (
        <div className="callout status-warn">
          <dl className="facts">
            <dt>Referred to</dt>
            <dd>{outcome.referred_to ?? "A data steward (no role named)"}</dd>
          </dl>
          <Reason code={outcome.reason_code} />
          <RunId id={envelope.invocation_id} />
        </div>
      )}

      {outcome.status === "failed" && (
        <div className="callout status-danger">
          <p>
            <strong>{envelope.problem?.title ?? "The run failed"}</strong>
          </p>
          {envelope.problem?.detail && <p className="problem-detail">{envelope.problem.detail}</p>}
          {slug && (
            <p className="muted">
              Problem type: <code>{slug}</code>
            </p>
          )}
          {slug === "input-not-accepted" && editButton}
          <RunId id={envelope.invocation_id} />
        </div>
      )}

      {outcome.status === "suspended" && (
        <NotBuilt title="Resuming a suspended run" issues={[72]}>
          <p>The run is waiting on a condition. Resuming it from here is not built yet.</p>
        </NotBuilt>
      )}

      {outcome.status === "succeeded" && (
        <>
          {envelope.payload ? (
            <ResultView
              payload={envelope.payload}
              schema={agent.payload ? agent.schemas[agent.payload] : undefined}
              derivations={agent.derivations}
              evidence={evidence}
              idPrefix={idPrefix}
            />
          ) : (
            <p>The agent reported its outcome without a result.</p>
          )}
          <NotBuilt title="Human review" issues={[72, 73]}>
            <p>
              Data Director marks every result for human review. Changes an agent proposes will
              wait here to be approved, edited or rejected, with a reason for the risky ones. An
              agent that only advises proposes no changes.
            </p>
          </NotBuilt>
        </>
      )}

      <EvidencePanel evidence={evidence} checks={checks} idPrefix={idPrefix} />

      <details className="run-facts">
        <summary>About this run</summary>
        <dl className="facts">
          <dt>Run id</dt>
          <dd>
            <code>{envelope.invocation_id}</code>
          </dd>
          <dt>Agent</dt>
          <dd>
            <code>{envelope.agent_id}</code> {envelope.agent_version}
          </dd>
          <dt>Completed</dt>
          <dd>{envelope.completed_at}</dd>
          <dt>Acted for</dt>
          <dd>{envelope.acting_for?.name ?? "Not recorded"}</dd>
          <dt>Policy</dt>
          <dd>
            <code>{envelope.policy_bundle_ref}</code>
          </dd>
          <dt>Grounding</dt>
          <dd>
            <code>{envelope.grounding_mode}</code>
          </dd>
        </dl>
      </details>
    </section>
  );
}
