/**
 * The facts of a project (docs/specs/projects.md, invariant 28): what check agents proposed about
 * it, for a person to confirm, change or reject, and what people decided. Every drafter in the
 * project is given the facts that stand, so that a draft leaves out a file a person excluded, or
 * asks before naming a place that may not be published. A proposal is never given to an agent.
 *
 * A person may also state a fact nobody proposed, change one that stands, or remove it. Whether
 * sensitive data may be published, and the licence, are an owner's to decide.
 */

import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { formatDateTime } from "../../format";
import {
  type FactProposal,
  type ProjectFact,
  type ProjectFacts,
  useFactsApi,
} from "../../project/facts";
import { Button } from "../ui/Button";
import { loadInto, message, type PanelLoad } from "./panelLoad";
import { FactDecisionForm } from "./FactDecisionForm";
import { blankFact } from "./FactFields";
import { KIND_LABELS, OWNERS_KINDS, describeFact } from "./factWording";

const HEADING_ID = "facts-heading";

type Load = PanelLoad<ProjectFacts>;

type Said = { text: string; ok: boolean };

function factKey(fact: ProjectFact): string {
  return `${fact.fact_kind}:${fact.fact_subject}`;
}

function OwnersNote({ fact }: { fact: ProjectFact }) {
  if (!OWNERS_KINDS.includes(fact.fact_kind)) return null;
  return <p className="hint">Only an owner of the project may decide this.</p>;
}

function Proposal({
  projectId,
  proposal,
  onDecided,
  onStale,
}: {
  projectId: string;
  proposal: FactProposal;
  onDecided: (value: ProjectFacts, said: string) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const { fact } = proposal;
  return (
    <article className="fact-card" aria-label={`${KIND_LABELS[fact.fact_kind]}: ${describeFact(fact)}`}>
      <h4>{KIND_LABELS[fact.fact_kind]}</h4>
      <p>{describeFact(fact)}</p>
      {fact.commitment_quote && (
        <figure className="fact-quote">
          <figcaption>The plan's words:</figcaption>
          <blockquote>{fact.commitment_quote}</blockquote>
        </figure>
      )}
      {fact.proposed_because && (
        <p>
          <strong>Why it was proposed:</strong> {fact.proposed_because}
        </p>
      )}
      <p className="hint">
        Proposed by {proposal.agent_id} on{" "}
        <time dateTime={proposal.proposed_at}>{formatDateTime(proposal.proposed_at)}</time>.
      </p>
      <OwnersNote fact={fact} />
      <FactDecisionForm
        projectId={projectId}
        proposal={proposal}
        initial={fact}
        onDecided={onDecided}
        onStale={onStale}
      />
    </article>
  );
}

function Decided({
  projectId,
  fact,
  busy,
  onRemove,
  onDecided,
  onStale,
}: {
  projectId: string;
  fact: ProjectFact;
  busy: boolean;
  onRemove: () => void;
  onDecided: (value: ProjectFacts, said: string) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const [changing, setChanging] = useState(false);
  return (
    <li className="fact-decided">
      <p>
        <strong>{KIND_LABELS[fact.fact_kind]}:</strong> {describeFact(fact)}
      </p>
      {changing ? (
        <FactDecisionForm
          projectId={projectId}
          initial={fact}
          onDecided={onDecided}
          onStale={onStale}
          onCancel={() => setChanging(false)}
        />
      ) : (
        <p className="actions">
          <Button size="small" onPress={() => setChanging(true)}>
            Change
          </Button>
          <Button size="small" variant="quiet" icon={Trash2} isPending={busy} onPress={onRemove}>
            Remove
          </Button>
        </p>
      )}
    </li>
  );
}

export function FactsPanel({ projectId, revision = 0 }: { projectId: string; revision?: number }) {
  const api = useFactsApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [said, setSaid] = useState<Said | null>(null);
  const [stating, setStating] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => loadInto((signal) => api.facts(projectId, signal), setLoad), [api, projectId, revision]);

  const decided = useCallback((value: ProjectFacts, text: string) => {
    setLoad({ state: "loaded", value });
    setStating(false);
    setSaid({ text, ok: true });
  }, []);

  // The proposal moved on, or is not the project's: read again, and say why nothing was recorded.
  const stale = useCallback(
    async (detail: string) => {
      try {
        setLoad({ state: "loaded", value: await api.facts(projectId) });
      } catch {
        // The warning below still says what happened.
      }
      setSaid({ text: `Nothing was recorded: ${detail} The facts have been read again.`, ok: false });
    },
    [api, projectId],
  );

  const remove = (fact: ProjectFact) => {
    setBusy(true);
    api
      .decideFact(projectId, {
        verdict: "rejected",
        fact: { fact_kind: fact.fact_kind, fact_subject: fact.fact_subject },
      })
      .then(
        (value) => decided(value, `Removed: ${describeFact(fact)}`),
        (error: unknown) => setSaid({ text: `Data Director could not remove it: ${message(error)}`, ok: false }),
      )
      .finally(() => setBusy(false));
  };

  const body = () => {
    if (load.state === "loading") return <p>Reading what the project holds…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the project's facts: {load.message}</p>
        </div>
      );
    }
    const { proposals, decisions } = load.value;
    return (
      <>
        <h3>Proposed by agents</h3>
        {proposals.length === 0 ? (
          <p>No agent has proposed anything that waits for a decision.</p>
        ) : (
          proposals.map((proposal) => (
            <Proposal
              key={proposal.proposal}
              projectId={projectId}
              proposal={proposal}
              onDecided={decided}
              onStale={stale}
            />
          ))
        )}
        <h3>Decided</h3>
        {decisions.length === 0 ? (
          <p>Nobody has decided any facts about this project yet.</p>
        ) : (
          <ul className="plain-list">
            {decisions.map((fact) => (
              <Decided
                key={factKey(fact)}
                projectId={projectId}
                fact={fact}
                busy={busy}
                onRemove={() => remove(fact)}
                onDecided={decided}
                onStale={stale}
              />
            ))}
          </ul>
        )}
        {stating ? (
          <FactDecisionForm
            projectId={projectId}
            initial={blankFact("file_inclusion")}
            isNew
            onDecided={decided}
            onStale={stale}
            onCancel={() => setStating(false)}
          />
        ) : (
          <p>
            <Button icon={Plus} onPress={() => setStating(true)}>
              Add a fact
            </Button>
          </p>
        )}
      </>
    );
  };

  return (
    <section className="facts" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Project facts</h2>
      <p className="hint">
        What agents found while checking this project, such as a duplicate file, coordinates that
        may need withholding or the funder, waits here for a person to confirm. Agents drafting the
        project's documents are given only what a person decided, never a proposal, so that a
        draft leaves out a file you excluded and asks before naming a place you withheld.
      </p>
      <div role="status" className={said ? `callout ${said.ok ? "status-ok" : "status-warn"}` : undefined}>
        {said && <p>{said.text}</p>}
      </div>
      {body()}
    </section>
  );
}
