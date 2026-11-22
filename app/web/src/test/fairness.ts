/**
 * FAIR reports for tests, built on the one the server stored in a project
 * (`fixtures/project-fairness-runs.json`, written by
 * `app/tests/test_project_runs_by_class.py`).
 */

import fixture from "../../fixtures/project-fairness-runs.json";
import type { ProjectRuns } from "../api/generated/responses";
import type { FairCheck, FairnessReport } from "../project/fairness";
import type { ProjectRunsApi } from "../project/projectRuns";
import type { Envelope } from "../run/types";

export const STORED = fixture as unknown as ProjectRuns;
export const LATEST_RUN = STORED.runs[0] as Envelope;

/** The stored report, with `changes` made to it. */
export function aReport(changes: Partial<FairnessReport> = {}): FairnessReport {
  return { ...(LATEST_RUN.payload as unknown as FairnessReport), ...changes };
}

/** The stored report with `check` met, and its principle's tally counting it. */
export function meeting(report: FairnessReport, check: string): FairnessReport {
  const found = report.checks.find((c) => c.check === check) as FairCheck;
  const group = found.principle.charAt(0);
  return {
    ...report,
    checks: report.checks.map((c) =>
      c.check === check ? { ...c, met: true } : c,
    ),
    next_steps: report.next_steps.filter((id) => id !== check),
    principle_tallies: report.principle_tallies.map((t) =>
      t.principle_group === group ? { ...t, tally_met: t.tally_met + 1 } : t,
    ),
  };
}

/** A run holding `report`, stored at `completedAt`. */
export function aRun(
  report: FairnessReport,
  completedAt: string,
  id = completedAt,
): Envelope {
  return {
    ...LATEST_RUN,
    invocation_id: id,
    completed_at: completedAt,
    payload: { ...report },
  };
}

/** A stand-in for the server that answers with `runs`, newest first. */
export function runsApi(runs: Envelope[] = []): ProjectRunsApi {
  return { runs: () => Promise.resolve({ runs } as ProjectRuns) };
}
