/**
 * The facts of a project (docs/specs/projects.md, invariant 28): what check agents proposed about
 * it, for a person to confirm, change or reject, and what people decided. Every drafter in the
 * project is given the facts that stand, so that a draft leaves out a file a person excluded, or
 * asks before naming a place that may not be published. A proposal is never given to an agent.
 *
 * A person may also state a fact nobody proposed, change one that stands, or remove it. Whether
 * sensitive data may be published, and the licence, are an owner's to decide.
 */

import { MessageCircle, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatDateTime } from "../../format";
import {
  type FactProposal,
  type ProjectFact,
  type ProjectFacts,
  factKey,
  useFactsApi,
} from "../../project/facts";
import { factsPath, homePath, Link, useLocation } from "../../route";
import { Button } from "../ui/Button";
import { loadInto, message, type PanelLoad } from "./panelLoad";
import { FactDecisionForm } from "./FactDecisionForm";
import { blankFact } from "./FactFields";
import { KIND_LABELS, OWNERS_KINDS, describeFact } from "./factWording";

const HEADING_ID = "facts-heading";

type Load = PanelLoad<ProjectFacts>;

type Said = { text: string; ok: boolean };

/** The facts a link named (`?fact=`, see `factsPath`), to mark and bring into view. */
function useLinkedFacts(): ReadonlySet<string> {
  const where = useLocation();
  const query = where.includes("?") ? where.slice(where.indexOf("?")) : "";
  const joined = new URLSearchParams(query).getAll("fact").join("\n");
  return useMemo(() => new Set(joined ? joined.split("\n") : []), [joined]);
}

function OwnersNote({ fact }: { fact: ProjectFact }) {
  if (!OWNERS_KINDS.includes(fact.fact_kind)) return null;
  return <p className="hint">Only an owner of the project may decide this.</p>;
}

/** What marks a fact a link named, so that focus may be moved to it. */
function linkedProps(linked: boolean) {
  return linked ? { tabIndex: -1, "data-linked": "" } : {};
}

function Proposal({
  projectId,
  proposal,
  linked,
  onDecided,
  onStale,
}: {
  projectId: string;
  proposal: FactProposal;
  linked: boolean;
  onDecided: (value: ProjectFacts, said: string) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const { fact } = proposal;
  return (
    <article
      {...linkedProps(linked)}
      className={linked ? "fact-card fact-target" : "fact-card"}
      aria-label={`${KIND_LABELS[fact.fact_kind]}: ${describeFact(fact)}`}
    >
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
      <p className="hint">
        <Link to={homePath({ fact: proposal.proposal })}>
          <MessageCircle aria-hidden="true" size={16} /> Discuss this with Data Director{" "}
          <span className="visually-hidden">in a new conversation: {describeFact(fact)}</span>
        </Link>
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
  linked,
  busy,
  onRemove,
  onDecided,
  onStale,
}: {
  projectId: string;
  fact: ProjectFact;
  linked: boolean;
  busy: boolean;
  onRemove: () => void;
  onDecided: (value: ProjectFacts, said: string) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const [changing, setChanging] = useState(false);
  return (
    <li {...linkedProps(linked)} className={linked ? "fact-decided fact-target" : "fact-decided"}>
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
          {/* Which document is the plan is changed on the Documents page (#1447). */}
          {fact.fact_kind !== "data_management_plan" && (
            <Button size="small" onPress={() => setChanging(true)}>
              Change
            </Button>
          )}
          <Button size="small" variant="quiet" icon={Trash2} isPending={busy} onPress={onRemove}>
            Remove
          </Button>
        </p>
      )}
    </li>
  );
}

/**
 * Says which facts a link named, and when none of them is here any more (decided and removed
 * since, say) says that rather than leaving the person to look for them.
 */
function LinkedNote({
  projectId,
  linked,
  facts,
}: {
  projectId: string;
  linked: ReadonlySet<string>;
  facts: ProjectFacts;
}) {
  if (linked.size === 0) return null;
  const here = new Set([...facts.proposals.map((p) => factKey(p.fact)), ...facts.decisions.map(factKey)]);
  const found = [...linked].filter((key) => here.has(key)).length;
  let said: string;
  if (found === 0) {
    said = "The facts you followed a link to are no longer here: someone may have removed them since.";
  } else if (found === 1) {
    said = "The fact you followed a link to is marked below.";
  } else {
    said = `The ${found} facts you followed a link to are marked below.`;
  }
  return (
    <p className="callout">
      {said} <Link to={factsPath(projectId)}>Show the facts without marks</Link>
    </p>
  );
}

export function FactsPanel({ projectId, revision = 0 }: { projectId: string; revision?: number }) {
  const api = useFactsApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [said, setSaid] = useState<Said | null>(null);
  const [stating, setStating] = useState(false);
  const [busy, setBusy] = useState(false);
  const linked = useLinkedFacts();
  const section = useRef<HTMLElement>(null);

  useEffect(() => loadInto((signal) => api.facts(projectId, signal), setLoad), [api, projectId, revision]);

  // A link to some of the facts, from the conversation or the project pane, lands on the first of
  // them once they are drawn: it is brought into view and focused, so a keyboard or screen reader
  // starts there too.
  const loaded = load.state === "loaded";
  useEffect(() => {
    if (!loaded || linked.size === 0) return;
    const first = section.current?.querySelector<HTMLElement>("[data-linked]");
    first?.scrollIntoView?.({ block: "start" });
    first?.focus({ preventScroll: true });
  }, [loaded, linked]);

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
        <LinkedNote projectId={projectId} linked={linked} facts={load.value} />
        <h3>Proposed by agents</h3>
        {proposals.length === 0 ? (
          <p>No agent has proposed anything that waits for a decision.</p>
        ) : (
          proposals.map((proposal) => (
            <Proposal
              key={proposal.proposal}
              projectId={projectId}
              proposal={proposal}
              linked={linked.has(factKey(proposal.fact))}
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
                linked={linked.has(factKey(fact))}
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
    <section ref={section} className="facts" aria-labelledby={HEADING_ID}>
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
