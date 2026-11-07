/**
 * Choosing a repository from `advisor.repository`'s shortlist (docs/specs/deposit.md, #400). Each
 * candidate the run shortlisted is named from the re3data record it rests on, with a button that
 * chooses it for the run's project. The shell sends only the run and the candidate's re3data
 * identifier; the server reads the repository's name and declared standards from the run's
 * evidence and resolves the requirements. What the choice resolved to, and any warning, is said in
 * the component's live region, with a link to the project's Repository panel.
 */

import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { type RepositoryChoice, useProjectApi } from "../../project/api";
import { Link } from "../../route";
import type { Envelope } from "../../run/types";
import { Button } from "../ui/Button";

export const REPOSITORY_ADVISOR = "advisor.repository";

interface Candidate {
  re3dataId: string;
  name: string;
}

/** The candidates a run shortlisted, each named from its re3data record in the run's evidence. */
export function candidatesOf(envelope: Envelope): Candidate[] {
  const records = new Map<string, string>();
  for (const item of envelope.evidence ?? []) {
    const content = item.content;
    if (content && typeof content.re3data_id === "string" && typeof content.name === "string") {
      records.set(item.source_id, content.name);
    }
  }
  const candidates = (envelope.payload?.candidates ?? []) as {
    grounded_on?: { source_id?: string }[];
  }[];
  const found: Candidate[] = [];
  for (const candidate of candidates) {
    const cited = (candidate.grounded_on ?? []).find(
      (g) => g.source_id !== undefined && records.has(g.source_id),
    );
    if (cited?.source_id) found.push({ re3dataId: cited.source_id, name: records.get(cited.source_id) ?? "" });
  }
  return found;
}

export function RepositoryShortlist({ envelope, idPrefix }: { envelope: Envelope; idPrefix: string }) {
  const api = useProjectApi();
  const projectId = envelope.project_id;
  const [sending, setSending] = useState<string | null>(null);
  const [chosen, setChosen] = useState<RepositoryChoice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const headingId = `${idPrefix}-choose-repository`;

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const candidates = candidatesOf(envelope);
  if (!projectId || candidates.length === 0) return null;

  async function choose(candidate: Candidate) {
    if (!projectId) return;
    setSending(candidate.re3dataId);
    setError(null);
    try {
      setChosen(await api.chooseRepository(projectId, envelope.invocation_id, candidate.re3dataId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSending(null);
    }
  }

  return (
    <section className="repository-shortlist" aria-labelledby={headingId}>
      <h4 id={headingId}>Choose a repository for this project</h4>
      <p className="hint">
        The deposit package is checked against what the repository you choose asks for. You can
        choose again later; the last choice counts.
      </p>
      <ul className="plain-list">
        {candidates.map((candidate) => (
          <li key={candidate.re3dataId}>
            {/* Not `isPending`: the press is short, and the result is said in the live region. */}
            <Button
              size="small"
              icon={Check}
              isDisabled={sending !== null}
              onPress={() => void choose(candidate)}
            >
              {sending === candidate.re3dataId ? "Choosing…" : `Choose ${candidate.name}`}
            </Button>
          </li>
        ))}
      </ul>
      {error && (
        <div role="alert" className="callout status-danger" ref={errorRef} tabIndex={-1}>
          <p>The repository was not chosen: {error}</p>
        </div>
      )}
      <div role="status" className={chosen ? "callout status-ok" : undefined}>
        {chosen && (
          <>
            <p>
              {chosen.repository_name} chosen for this project.{" "}
              <Link to={`/projects/${encodeURIComponent(projectId)}?doc=repository`}>
                See what it asks for
              </Link>
            </p>
            {chosen.warnings.length > 0 && (
              <ul>
                {chosen.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  );
}
