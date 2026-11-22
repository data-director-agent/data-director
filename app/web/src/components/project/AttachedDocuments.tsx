/**
 * The documents attached to a project, on its Documents page, and which one is the project's Data
 * Management Plan (docs/specs/projects.md, invariant 32; #1447). Which document is the plan is a
 * project fact a person decides: **Mark as the Data Management Plan** states it, replacing any
 * plan marked before, and **Not the plan** removes it (`POST /api/projects/{id}/facts/decisions`).
 * The list is then read again, since the server says which document is the plan. A proposal of
 * the plan by the DMP check waits on the Project facts panel.
 */

import { useState } from "react";

import { type DocumentationSummary, describeSize } from "../../conversation/documentation";
import { useProjectApi } from "../../project/api";
import { PLAN_SUBJECT, planFact, useFactsApi } from "../../project/facts";
import { errorMessage } from "../../run/api";
import { useAnnounce } from "../ui/Announcer";
import { Button } from "../ui/Button";

export function AttachedDocuments({
  projectId,
  held,
  onChange,
}: {
  projectId: string;
  held: readonly DocumentationSummary[];
  /** The documents as the server lists them after a change. */
  onChange: (held: DocumentationSummary[]) => void;
}) {
  const facts = useFactsApi();
  const api = useProjectApi();
  const announce = useAnnounce();
  const [busy, setBusy] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  async function decide(document: DocumentationSummary, plan: boolean) {
    setBusy(document.documentation_digest);
    try {
      await facts.decideFact(
        projectId,
        plan
          ? { verdict: "changed", fact: planFact(document.documentation_digest) }
          : { verdict: "rejected", fact: { fact_kind: "data_management_plan", fact_subject: PLAN_SUBJECT } },
      );
      onChange(await api.documentation(projectId));
      setRefused(null);
      announce(
        plan
          ? `${document.documentation_name} is marked as the project's Data Management Plan.`
          : `${document.documentation_name} is no longer marked as the project's Data Management Plan.`,
      );
    } catch (e) {
      setRefused(`Nothing was changed: ${errorMessage(e)}`);
    } finally {
      setBusy(null);
    }
  }

  if (held.length === 0) return null;
  return (
    <section aria-label="Attached documents" className="attached-documents">
      <h2 className="attached-documents-heading">Attached documents</h2>
      {refused && <p role="alert">{refused}</p>}
      <ul className="plain-list">
        {held.map((d) => (
          <li key={`${d.documentation_name}:${d.documentation_digest}`}>
            {d.documentation_name} <span className="hint">({describeSize(d.documentation_size)})</span>
            {d.documentation_is_plan ? (
              <>
                {" "}
                <strong className="plan-badge">Data Management Plan</strong>{" "}
                <Button
                  size="small"
                  variant="quiet"
                  isPending={busy === d.documentation_digest}
                  onPress={() => void decide(d, false)}
                >
                  Not the plan
                </Button>
              </>
            ) : (
              <>
                {" "}
                <Button
                  size="small"
                  variant="quiet"
                  isPending={busy === d.documentation_digest}
                  onPress={() => void decide(d, true)}
                >
                  Mark as the Data Management Plan
                </Button>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
