/**
 * The transcript: an ordered list of turns, each the person's message and the agent's reply. The
 * person's part sits on a surface at the end edge, the agent's at the start edge beside a rule, so
 * the two differ by surface and position as well as by their labels (WCAG 1.4.1). Each reply is
 * headed by the agent's name from its card, with `agent_id@agent_version` beneath it; a change of
 * version since an earlier turn is marked (docs/specs/orchestration.md), and each delegated child
 * is a card that opens its run, with its evidence, in place. Abstained, referred and failed
 * replies use the run view's outcome wording, not a generic error. A turn on which the project's
 * inventory changed, as when the researcher attached one, shows it as a chip (#443), and so does
 * each document the project gained on the turn, by name and size, never its text. A document
 * version the turn or one of its children drafted, as the project log records it, is a card on
 * the turn, before the runs that are its evidence.
 *
 * A reply that asks a choice question shows it beneath the reply: as choices on the latest turn,
 * disabled while a message is being sent, and read-only with the answer marked on every earlier
 * turn.
 */

import "./Transcript.css";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo } from "react";

import type { AttachedDocument, DocumentationSummary } from "../../conversation/documentation";
import type {
  AttachedInventory,
  InventorySource,
  InventorySummary,
} from "../../conversation/inventory";
import { type ReplyAnswers, replyOwnText, replyQuestions } from "../../conversation/question";
import type { Conversation, ConversationTurn } from "../../conversation/types";
import {
  type ProjectDocument,
  type ProjectDocuments,
  type ProjectSummary,
  type RepositoryRequirements,
  useProjectApi,
} from "../../project/api";
import { draftedBy } from "../../project/drafted";
import { shortlistOf } from "../../project/shortlist";
import type { AgentView } from "../../manifest/normalise";
import { Link } from "../../route";
import { OUTCOME, REASON } from "../../manifest/wording";
import type { Envelope } from "../../run/types";
import { Button } from "../ui/Button";
import { Markdown } from "../ui/Markdown";
import { DocumentCard } from "./DocumentCard";
import { AskedQuestions, QuestionSeries } from "./QuestionSeries";
import { DocumentChip } from "./DocumentChip";
import { InventoryChip } from "./InventoryChip";
import { Pending } from "./Pending";
import { RepositoryShortlist } from "./RepositoryShortlist";
import { RunDetail } from "./RunDetail";
import { nameOf, Speaker } from "./Speaker";

function replyText(conversation: Conversation, turn: ConversationTurn): string {
  // A Reply's own text: the history adds the question after it, which is shown as choices.
  const own = replyOwnText(turn.envelope);
  if (own !== null) return own;
  const entry = conversation.history.find(
    (h) => h.role === "agent" && h.turn_invocation_id === turn.invocation_id,
  );
  return entry?.turn_text ?? turn.envelope.outcome.statement;
}

/** The project's inventory as the turn's agent was told of it, when it differs from the turn
 * before: the turn it was given on. */
function inventoryGiven(conversation: Conversation, index: number): InventorySummary | null {
  const of = (turn: ConversationTurn | undefined) =>
    turn ? conversation.inputs[turn.invocation_id]?.project_inventory : undefined;
  const here = of(conversation.turns[index]);
  if (!here) return null;
  return here.inventory_digest === of(conversation.turns[index - 1])?.inventory_digest ? null : here;
}

/** The documents the turn's agent was told of that the turn before's was not: those given on it. */
function documentsGiven(conversation: Conversation, index: number): DocumentationSummary[] {
  const of = (turn: ConversationTurn | undefined) =>
    (turn ? conversation.inputs[turn.invocation_id]?.project_documentation : undefined) ?? [];
  const key = (d: DocumentationSummary) => `${d.documentation_name}\u0000${d.documentation_digest}`;
  const before = new Set(of(conversation.turns[index - 1]).map(key));
  return of(conversation.turns[index]).filter((d) => !before.has(key(d)));
}

function OutcomeNote({ envelope }: { envelope: Envelope }) {
  const { status, reason_code: code } = envelope.outcome;
  if (status === "succeeded") return null;
  const reason = code ? REASON[code] : undefined;
  return (
    <p className="muted">
      {OUTCOME[status].label}.{" "}
      {reason ? `${reason.meaning} ${reason.next}` : envelope.outcome.statement}
    </p>
  );
}

/**
 * A delegated child as a disclosure: its button shows or hides the run inside the card, and
 * focus stays on the button. Which run is open is the `run` query parameter, so only one is
 * open at a time and Back and reload keep it.
 */
function ChildCard({
  child,
  agents,
  onToggle,
  selected,
  project,
}: {
  child: Envelope;
  agents: AgentView[];
  onToggle: (child: Envelope) => void;
  selected: boolean;
  project: ProjectSummary | null | undefined;
}) {
  const { label, tone } = OUTCOME[child.outcome.status];
  // TODO(#72, #73): a suspended run is the only sign of review waiting until the gate exists.
  const waiting = child.outcome.status === "suspended";
  const name = nameOf(agents, child.agent_id);
  const regionId = `run-${child.invocation_id}`;
  return (
    <li className="callout child-card" {...(selected ? { "aria-current": "true" as const } : {})}>
      <Speaker agents={agents} agentId={child.agent_id} agentVersion={child.agent_version} />
      <p>
        <span className={`status status-${tone}`}>{label}</span>
        {waiting && (
          <>
            {" "}
            <span className="status status-warn">⏸ Waiting for review</span>
          </>
        )}
      </p>
      <Button
        size="small"
        icon={selected ? ChevronUp : ChevronDown}
        aria-expanded={selected}
        aria-controls={regionId}
        onPress={() => onToggle(child)}
      >
        {selected ? "Hide the run" : "Show the run"}
        <span className="visually-hidden"> of {name}</span>
      </Button>{" "}
      <Link to={`/agents?agent=${encodeURIComponent(child.agent_id)}`}>
        About this agent<span className="visually-hidden"> {name}</span>
      </Link>
      <div id={regionId} className="child-run" hidden={!selected}>
        {selected && (
          <RunDetail
            invocationId={child.invocation_id}
            agents={agents}
            idPrefix={regionId}
            project={project}
          />
        )}
      </div>
    </li>
  );
}

export function Transcript({
  conversation,
  agents,
  onToggleRun,
  selectedRun = null,
  pending = null,
  documents = null,
  onAnswer,
  onDocumentAnswered,
  chosenRepository = null,
  onRepositoryChosen,
  project,
}: {
  conversation: Conversation | null;
  agents: AgentView[];
  onToggleRun: (child: Envelope) => void;
  selectedRun?: string | null;
  /** The project's documents, as last read; null until they have been. */
  documents?: ProjectDocument[] | null;
  /** A message sent and not yet answered, shown after the turns with a sign that a reply is coming. */
  pending?: {
    agentId: string;
    message: string;
    inventory?: AttachedInventory | null;
    document?: AttachedDocument | null;
  } | null;
  /** Sends the answers to the latest turn's questions; without it, none can be answered. */
  onAnswer?: (answers: ReplyAnswers, text: string) => void;
  /** Takes the project's documents after the researcher answers a draft's questions; without
   * it, no draft's questions can be answered. */
  onDocumentAnswered?: (value: ProjectDocuments) => void;
  /** The re3data identifier of the repository the project chose last, if any. */
  chosenRepository?: string | null;
  /** Takes the requirements a repository the researcher chose from a shortlist resolved to;
   * without it, no shortlist can be chosen from. */
  onRepositoryChosen?: (requirements: RepositoryRequirements) => void;
  /** The conversation's project as the projects list describes it, once that has been read. */
  project?: ProjectSummary | null | undefined;
}) {
  // Only the inventory the project holds now is served, so only its chip opens it.
  const projectId = conversation?.project_id;
  // The project a delegated run belongs to, through the conversation that started it: null when
  // the conversation has none, and unknown until the projects list describes the one it has.
  const runProject = !conversation
    ? undefined
    : !projectId
      ? null
      : project?.project_id === projectId
        ? project
        : undefined;
  const current = conversation?.inventory?.digest;
  const projectApi = useProjectApi();
  const source = useMemo<InventorySource | undefined>(
    () => (projectId ? { load: (signal) => projectApi.inventory(projectId, signal) } : undefined),
    [projectApi, projectId],
  );
  return (
    // The numbers are dropped (Transcript.css), and WebKit then stops announcing a list unless
    // its role is given, so it is, though it is the element's own.
    // eslint-disable-next-line jsx-a11y/no-redundant-roles
    <ol className="transcript" role="list" aria-label="Conversation">
      {conversation?.turns.map((turn, index) => {
        const given = inventoryGiven(conversation, index);
        const attachedDocuments = documentsGiven(conversation, index);
        const drafted =
          projectId && documents
            ? draftedBy(
                [turn.invocation_id, ...turn.children.map((child) => child.invocation_id)],
                documents,
              )
            : [];
        const questions = replyQuestions(turn.envelope);
        const latest = index === conversation.turns.length - 1;
        const next = conversation.turns[index + 1];
        const answers = next ? (conversation.inputs[next.invocation_id]?.reply_answers ?? null) : null;
        const shortlists = [turn.envelope, ...turn.children]
          .map((envelope) => ({ envelope, shortlist: shortlistOf(envelope) }))
          .filter(({ shortlist }) => shortlist.length > 0);
        return (
        <li key={turn.invocation_id} className="turn">
          <div className="turn-person">
            <Speaker />
            <p>{conversation.inputs[turn.invocation_id]?.message_text}</p>
            {given && (
              <p>
                <InventoryChip
                  fileCount={given.inventory_file_count}
                  madeAt={given.inventory_made_at}
                  source={given.inventory_digest === current ? source : undefined}
                />
              </p>
            )}
            {attachedDocuments.map((d) => (
              <p key={`${d.documentation_name}-${d.documentation_digest}`}>
                <DocumentChip name={d.documentation_name} size={d.documentation_size} />
              </p>
            ))}
          </div>
          <div className="turn-agent">
            {conversation.version_changes
              .filter((c) => c.turn_index === turn.turn_index)
              .map((c) => (
                <p key={`${c.agent_id}-${c.to}`} className="callout status-warn">
                  {nameOf(agents, c.agent_id) !== c.agent_id && `${nameOf(agents, c.agent_id)}, `}
                  <code>{c.agent_id}</code>, changed version from <code>{c.from}</code> to{" "}
                  <code>{c.to}</code> since an earlier turn.
                </p>
              ))}
            <Speaker agents={agents} agentId={turn.agent_id} agentVersion={turn.agent_version} />
            <div className="markdown">
              <Markdown>{replyText(conversation, turn)}</Markdown>
            </div>
            {questions.length > 0 &&
              (latest && onAnswer ? (
                // Kept while a message is sent, disabled, so a failed send keeps the answers.
                <QuestionSeries
                  key={turn.invocation_id}
                  questions={questions}
                  askedBy={turn.invocation_id}
                  askedByName={nameOf(agents, turn.agent_id)}
                  onAnswer={onAnswer}
                  disabled={pending !== null}
                />
              ) : (
                <AskedQuestions
                  questions={questions}
                  answers={answers?.answer_to === turn.invocation_id ? answers : null}
                />
              ))}
            <OutcomeNote envelope={turn.envelope} />
            {projectId && drafted.length > 0 && (
              <ul aria-label="Documents drafted on this turn" className="plain-list">
                {drafted.map((d) => (
                  <DocumentCard
                    key={`${d.document.document_id}-${d.version.version}`}
                    projectId={projectId}
                    drafted={d}
                    idPrefix={`drafted-${turn.invocation_id}-${d.document.document_id}-${d.version.version}`}
                    {...(onDocumentAnswered ? { onAnswered: onDocumentAnswered } : {})}
                  />
                ))}
              </ul>
            )}
            {projectId &&
              onRepositoryChosen &&
              shortlists.map(({ envelope, shortlist }) => (
                <RepositoryShortlist
                  key={`shortlist-${envelope.invocation_id}`}
                  projectId={projectId}
                  shortlist={shortlist}
                  chosenId={chosenRepository}
                  idPrefix={`shortlist-${envelope.invocation_id}`}
                  onChosen={onRepositoryChosen}
                />
              ))}
            {turn.children.length > 0 && (
              <ul aria-label={`Agents ${turn.agent_id} delegated to`} className="plain-list">
                {turn.children.map((child) => (
                  <ChildCard
                    key={child.invocation_id}
                    child={child}
                    agents={agents}
                    onToggle={onToggleRun}
                    selected={child.invocation_id === selectedRun}
                    project={runProject}
                  />
                ))}
              </ul>
            )}
          </div>
        </li>
        );
      })}
      {pending && (
        <Pending
          agentId={pending.agentId}
          agentName={nameOf(agents, pending.agentId)}
          message={pending.message}
          inventory={pending.inventory ?? null}
          document={pending.document ?? null}
        />
      )}
    </ol>
  );
}
