/**
 * What a run came to, routed on the envelope's outcome status (checklist items 4 and 5).
 *
 * Succeeded shows the result and the evidence it rests on. Abstained and referred are answers in
 * their own right, each with what it means and what to do next, not errors. Failed shows the
 * problem as the harness stated it. Nothing a run proposes waits for review yet (#394), whether or
 * not the conversation that started it belongs to a project; where it does, the project is named
 * and linked (#755). That, and resuming a suspended run, are drawn in place (#72, #73).
 */

import "./Outcome.css";

import { type Ref, useState } from "react";

import { Copy, RotateCcw } from "lucide-react";
import type { AgentView } from "../../manifest/normalise";
import { MODEL_ACCOUNT, OUTCOME, REASON } from "../../manifest/wording";
import { problemSlug } from "../../run/problem";
import type { ProjectSummary } from "../../project/api";
import { projectName } from "../../project/name";
import { Link } from "../../route";
import type { ModelCall, RunResult } from "../../run/types";
import { NotBuilt } from "../NotBuilt";
import { Button } from "../ui/Button";
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
      <Button variant="quiet" size="small" icon={Copy} onPress={() => void copy()}>
        Copy run id
      </Button>{" "}
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

/** Each model call the run recorded, the model it was routed from if the profile's model map
 * routed it, and whose account paid for it, never whose. */
function ModelCalls({ calls }: { calls: ModelCall[] }) {
  if (calls.length === 0) return <dd>None</dd>;
  return (
    <dd>
      <ul className="model-calls">
        {calls.map((c, i) => (
          <li key={`${c.prompt_digest}-${i}`}>
            <code>{c.model_id}</code>
            {c.model_declared ? (
              <>
                {" "}
                in place of <code>{c.model_declared}</code>
              </>
            ) : null}
            , paid for by{" "}
            {c.model_account
              ? MODEL_ACCOUNT[c.model_account]
              : "an account the run did not record"}
          </li>
        ))}
      </ul>
    </dd>
  );
}

/**
 * Where a succeeded run's result goes. The run store records no project, so this is the project
 * of the conversation that started the run: named and linked when it is known, said to be none
 * when the conversation has none, and left unsaid when it is not known.
 */
function HumanReview({ project }: { project: ProjectSummary | null | undefined }) {
  return (
    <NotBuilt title="Human review" issues={[72, 73, 394]}>
      <p>
        Nothing waits for approval.{" "}
        {project ? (
          <>
            This run is part of the project{" "}
            <Link to={`/projects/${encodeURIComponent(project.project_id)}`}>
              {projectName(project)}
            </Link>
            , but what it proposes is not reviewed there yet, so its result is kept only with the
            run, and nothing is changed until a person acts on it.
          </>
        ) : project === null ? (
          <>
            This run is not part of a project, so its result is kept only with the run, and
            nothing is changed until a person acts on it.
          </>
        ) : (
          <>
            Its result is kept only with the run, and nothing is changed until a person acts on
            it.
          </>
        )}
      </p>
    </NotBuilt>
  );
}

// eslint-disable-next-line complexity -- recorded debt: split it, do not add to it (docs/architecture-review.md)
export function Outcome({
  result,
  agent,
  idPrefix,
  headingRef,
  onEditInput,
  project,
}: {
  result: RunResult;
  agent: AgentView;
  idPrefix: string;
  headingRef?: Ref<HTMLHeadingElement>;
  onEditInput?: () => void;
  /** The project of the conversation that started the run; null if it has none, and left out
   * if that is not known. */
  project?: ProjectSummary | null | undefined;
}) {
  const { envelope, checks } = result;
  const { outcome } = envelope;
  const { label, tone } = OUTCOME[outcome.status];
  const headingId = `${idPrefix}-outcome`;
  const evidence = envelope.evidence ?? [];
  const slug = problemSlug(envelope.problem?.type);
  const editButton = onEditInput && (
    <p>
      <Button icon={RotateCcw} onPress={onEditInput}>Edit the input and run again</Button>
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
              className={agent.payload}
              derivations={agent.derivations}
              evidence={evidence}
              idPrefix={idPrefix}
            />
          ) : (
            <p>The agent reported its outcome without a result.</p>
          )}
          <HumanReview project={project} />
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
          <dt>Model calls</dt>
          <ModelCalls calls={envelope.telemetry?.model_calls ?? []} />
        </dl>
      </details>
    </section>
  );
}
