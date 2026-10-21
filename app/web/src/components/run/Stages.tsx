/**
 * The conductor's stages for one run, each with a word for its state (checklist item 1).
 *
 * The stages are read back after the run has ended (run/stages.ts), and the page says so: live
 * progress needs the AG-UI stream (#68, #69).
 */

import { STAGE_STATE } from "../../manifest/wording";
import type { Stage, StageState } from "../../run/stages";
import { IssueLinks } from "../NotBuilt";

const MARK: Record<StageState, string> = {
  waiting: "○",
  running: "●",
  passed: "✓",
  failed: "✗",
  stopped: "!",
  finished: "✓",
  "not-reached": "–",
  "nothing-to-check": "–",
  "not-built": "◌",
};

export function Stages({ stages, inferred }: { stages: Stage[]; inferred: boolean }) {
  return (
    <section className="stages-section" aria-label="Progress">
      <h4>Progress</h4>
      {inferred && (
        <p className="hint">
          Read back after the run ended. Watching each stage as it happens is not built yet (
          <IssueLinks issues={[68, 69]} />
          ).
        </p>
      )}
      <ol className="stages">
        {stages.map((s) => {
          const { label, tone } = STAGE_STATE[s.state];
          return (
            <li key={s.id} className={`stage stage-${s.state}`}>
              <span className="stage-mark" aria-hidden="true">
                {MARK[s.state]}
              </span>
              <span className="stage-name">{s.label}</span>
              <span className={tone === "plain" ? "stage-state" : `status status-${tone}`}>
                {label}
              </span>
              {(s.detail || s.issues) && (
                <span className="stage-detail">
                  {s.detail}
                  {s.issues && (
                    <>
                      {" "}
                      (<IssueLinks issues={s.issues} />)
                    </>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
