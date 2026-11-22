/**
 * What the signed-in person keeps from their own public ORCID record in a project
 * (docs/specs/projects.md, invariant 27), on their own entry among the project's people.
 *
 * They bring in their record and tick what to keep; nothing is ticked until they tick it, and
 * nothing is kept until they press Keep. The shell sends only what was ticked, by section and
 * ORCID put-code; the server reads the record from ORCID again and keeps ORCID's own words.
 * Keeping again replaces what they kept before, and Withdraw stops agents being given it.
 */

import { useState } from "react";

import { useProjectApi } from "../../project/api";
import type { ResearcherRecord } from "../../project/researcher";
import { OrcidIcon } from "../ui/BrandIcon";
import { Button } from "../ui/Button";
import { message, type PanelLoad } from "./panelLoad";
import { ResearcherChooser } from "./ResearcherChooser";
import { choiceOf } from "./researcherFacts";

export function MyOrcidFacts({
  projectId,
  mine,
  onChanged,
  onSaid,
}: {
  projectId: string;
  /** What they kept already, if anything. */
  mine: ResearcherRecord | undefined;
  /** Called once the server has kept or withdrawn their facts. */
  onChanged: () => void;
  onSaid: (said: { text: string; ok: boolean }) => void;
}) {
  const api = useProjectApi();
  const [offered, setOffered] = useState<PanelLoad<ResearcherRecord> | null>(null);
  const [busy, setBusy] = useState(false);

  const bringIn = () => {
    setOffered({ state: "loading" });
    api.orcidRecord().then(
      (value) => setOffered({ state: "loaded", value }),
      (error: unknown) => setOffered({ state: "failed", message: message(error) }),
    );
  };

  const change = (action: Promise<ResearcherRecord[]>, done: string) => {
    setBusy(true);
    action.then(
      () => {
        setBusy(false);
        setOffered(null);
        onSaid({ text: done, ok: true });
        onChanged();
      },
      (error: unknown) => {
        setBusy(false);
        onSaid({
          text: `Data Director could not do that: ${message(error)}`,
          ok: false,
        });
      },
    );
  };

  const withdraw = mine && (
    <Button
      variant="quiet"
      size="small"
      isPending={busy}
      onPress={() =>
        change(api.withdrawResearcher(projectId), "Agents in this project are no longer given what you kept.")
      }
    >
      Withdraw what you kept
    </Button>
  );

  const actions = (
    <p className="member-actions">
      <Button size="small" onPress={bringIn}>
        <OrcidIcon className="brand-icon" />{" "}
        {mine ? "Change what you keep from your ORCID record" : "Bring in facts from your ORCID record"}
      </Button>
      {withdraw}
    </p>
  );
  if (offered === null) return actions;
  if (offered.state === "loading") return <p>Reading your public ORCID record…</p>;
  if (offered.state === "failed") {
    return (
      <>
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read your ORCID record: {offered.message}</p>
        </div>
        {actions}
      </>
    );
  }
  return (
    <ResearcherChooser
      offered={offered.value}
      initial={choiceOf(mine)}
      busy={busy}
      onCancel={() => setOffered(null)}
      onKeep={(choice) =>
        change(api.keepResearcher(projectId, choice), "Kept. Agents in this project are given what you ticked.")
      }
    />
  );
}
