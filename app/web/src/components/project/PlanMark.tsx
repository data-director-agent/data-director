/**
 * Whether an attached document is the project's Data Management Plan, in the Documents tab's
 * reader (docs/specs/projects.md, invariant 32; #1447). Which document is the plan is a project
 * fact a person decides: **Mark as the Data Management Plan** states it, replacing any plan marked
 * before, and **Not the plan** removes it (`POST /api/projects/{id}/facts/decisions`). The
 * documents are then read again, since the server says which one is the plan. A proposal of the
 * plan by the DMP check waits on the Project facts panel.
 */

import { useState } from "react";

import type { DocumentationSummary } from "../../conversation/documentation";
import { useProjectApi } from "../../project/api";
import { PLAN_SUBJECT, planFact, useFactsApi } from "../../project/facts";
import { errorMessage } from "../../run/api";
import { useAnnounce } from "../ui/Announcer";
import { Button } from "../ui/Button";

export function PlanMark({
  projectId,
  document,
  onChange,
}: {
  projectId: string;
  document: DocumentationSummary;
  /** The documents as the server lists them after a change. */
  onChange: (held: DocumentationSummary[]) => void;
}) {
  const facts = useFactsApi();
  const api = useProjectApi();
  const announce = useAnnounce();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const plan = document.documentation_is_plan === true;
  const name = document.documentation_name;

  async function decide() {
    setBusy(true);
    try {
      await facts.decideFact(
        projectId,
        plan
          ? {
              verdict: "rejected",
              fact: {
                fact_kind: "data_management_plan",
                fact_subject: PLAN_SUBJECT,
              },
            }
          : {
              verdict: "changed",
              fact: planFact(document.documentation_digest),
            },
      );
      onChange(await api.documentation(projectId));
      setRefused(null);
      announce(
        plan
          ? `${name} is no longer marked as the project's Data Management Plan.`
          : `${name} is marked as the project's Data Management Plan.`,
      );
    } catch (e) {
      setRefused(`Nothing was changed: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <p className="plan-mark">
      {plan && <strong className="plan-badge">Data Management Plan</strong>}{" "}
      <Button
        size="small"
        variant="quiet"
        isPending={busy}
        onPress={() => void decide()}
      >
        {plan ? "Not the plan" : "Mark as the Data Management Plan"}
      </Button>
      {refused && <span role="alert"> {refused}</span>}
    </p>
  );
}
